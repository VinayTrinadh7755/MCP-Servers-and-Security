from __future__ import annotations

import asyncio
import sqlite3

import pytest

from task4.db.connection import init
from task4.limiter import TokenLimiter


@pytest.mark.asyncio
async def test_fifty_concurrent_reservations_never_exceed_cap(tmp_path) -> None:
    path = tmp_path / "usage.db"
    await init(path)
    limiter = TokenLimiter(limit=50_000, path=path, race_probe_delay=0.01)
    decisions = await asyncio.gather(
        *(limiter.try_reserve("tenant-a", 1_000) for _ in range(60))
    )
    admitted = [decision for decision in decisions if decision.allowed]
    denied = [decision for decision in decisions if not decision.allowed]
    assert len(admitted) == 50
    assert len(denied) == 10
    assert sum(1_000 for _ in admitted) == 50_000
    assert all(decision.current_usage == 50_000 for decision in denied)


@pytest.mark.asyncio
async def test_exact_limit_reconcile_overage_and_release(tmp_path) -> None:
    path = tmp_path / "usage.db"
    await init(path)
    limiter = TokenLimiter(limit=100, path=path)
    exact = await limiter.try_reserve("tenant-a", 100)
    assert exact.allowed
    await limiter.reconcile(exact.request_id, 110)
    denied = await limiter.try_reserve("tenant-a", 1)
    assert not denied.allowed

    other = await limiter.try_reserve("tenant-b", 100)
    assert other.allowed
    await limiter.release(other.request_id)
    replacement = await limiter.try_reserve("tenant-b", 100)
    assert replacement.allowed


@pytest.mark.asyncio
async def test_window_slides_at_exact_boundary_and_reports_retry_after(tmp_path) -> None:
    path = tmp_path / "usage.db"
    await init(path)
    now = [1_000_000]
    limiter = TokenLimiter(limit=100, window_ms=60_000, path=path, clock_ms=lambda: now[0])
    assert (await limiter.try_reserve("tenant-a", 100)).allowed
    initial_denial = await limiter.try_reserve("tenant-a", 1)
    assert initial_denial.retry_after_seconds == 60
    now[0] += 20_000
    later_denial = await limiter.try_reserve("tenant-a", 1)
    assert later_denial.retry_after_seconds == 40
    now[0] += 39_001
    denied = await limiter.try_reserve("tenant-a", 1)
    assert not denied.allowed
    assert denied.retry_after_seconds == 1
    now[0] += 999
    assert (await limiter.try_reserve("tenant-a", 100)).allowed


@pytest.mark.asyncio
async def test_tenant_isolation_and_eviction_bound_storage(tmp_path) -> None:
    path = tmp_path / "usage.db"
    await init(path)
    now = [1_000_000]
    limiter = TokenLimiter(limit=10, window_ms=100, path=path, clock_ms=lambda: now[0])
    assert (await limiter.try_reserve("tenant-a", 10)).allowed
    assert (await limiter.try_reserve("tenant-b", 10)).allowed
    assert not (await limiter.try_reserve("tenant-a", 1)).allowed

    for index in range(250):
        now[0] += 101
        assert (await limiter.try_reserve(f"tenant-{index}", 1)).allowed
    connection = sqlite3.connect(path)
    try:
        count = connection.execute("SELECT COUNT(*) FROM token_usage").fetchone()[0]
    finally:
        connection.close()
    assert count == 1


@pytest.mark.asyncio
async def test_reconcile_downward_frees_capacity_immediately(tmp_path) -> None:
    path = tmp_path / "usage.db"
    await init(path)
    limiter = TokenLimiter(limit=5_000, path=path)
    reservation = await limiter.try_reserve("tenant-a", 5_000)
    assert reservation.allowed
    await limiter.reconcile(reservation.request_id, 100)
    freed = await limiter.try_reserve("tenant-a", 4_900)
    assert freed.allowed
    assert freed.current_usage == 5_000


@pytest.mark.asyncio
async def test_orphan_reservation_counts_until_window_eviction(tmp_path) -> None:
    path = tmp_path / "usage.db"
    await init(path)
    now = [1_000_000]
    limiter = TokenLimiter(limit=100, window_ms=60_000, path=path, clock_ms=lambda: now[0])
    orphan = await limiter.try_reserve("tenant-a", 100)
    assert orphan.allowed
    assert not (await limiter.try_reserve("tenant-a", 1)).allowed
    now[0] += 60_000
    assert (await limiter.try_reserve("tenant-a", 100)).allowed


@pytest.mark.asyncio
async def test_reconcile_and_reserve_are_serialized_by_sqlite(tmp_path) -> None:
    path = tmp_path / "usage.db"
    await init(path)
    first = TokenLimiter(limit=5_000, path=path)
    second = TokenLimiter(limit=5_000, path=path)
    reservation = await first.try_reserve("tenant-a", 5_000)
    await asyncio.gather(
        first.reconcile(reservation.request_id, 100),
        second.try_reserve("tenant-a", 4_900),
    )
    connection = sqlite3.connect(path)
    try:
        total = connection.execute(
            "SELECT SUM(tokens) FROM token_usage WHERE tenant_key = ?", ("tenant-a",)
        ).fetchone()[0]
    finally:
        connection.close()
    assert total <= 5_000


@pytest.mark.asyncio
async def test_denial_writes_no_row_and_global_eviction_cleans_idle_tenants(tmp_path) -> None:
    path = tmp_path / "usage.db"
    await init(path)
    connection = sqlite3.connect(path)
    try:
        connection.executemany(
            "INSERT INTO token_usage(request_id, tenant_key, ts_ms, tokens, status) "
            "VALUES (?, ?, ?, ?, 'reconciled')",
            [(f"stale-{index}", f"idle-{index}", 1, 1) for index in range(1_000)],
        )
        connection.commit()
    finally:
        connection.close()

    now = [3_600_001]
    limiter = TokenLimiter(limit=1, window_ms=60_000, path=path, clock_ms=lambda: now[0])
    current = await limiter.try_reserve("current", 1)
    assert current.allowed
    denied = await limiter.try_reserve("current", 1)
    assert not denied.allowed
    connection = sqlite3.connect(path)
    try:
        count = connection.execute("SELECT COUNT(*) FROM token_usage").fetchone()[0]
    finally:
        connection.close()
    assert count == 1
