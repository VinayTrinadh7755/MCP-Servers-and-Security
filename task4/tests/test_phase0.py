from __future__ import annotations

import asyncio
import sqlite3

import pytest

from task4.db.connection import connect, init
from task4.providers.mock_provider import app as provider_app


@pytest.mark.asyncio
async def test_database_init_is_idempotent_and_enables_wal(tmp_path) -> None:
    path = tmp_path / "usage.db"
    assert await init(path) == path.resolve()
    assert await init(path) == path.resolve()

    connection = sqlite3.connect(path)
    try:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        table = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='token_usage'"
        ).fetchone()
        indexes = connection.execute("PRAGMA index_list(token_usage)").fetchall()
    finally:
        connection.close()
    assert table is not None
    assert "status" in table[0]
    assert any(row[1] == "idx_token_usage_tenant_ts" for row in indexes)


@pytest.mark.asyncio
async def test_two_connections_open_concurrently(tmp_path) -> None:
    path = tmp_path / "usage.db"
    await init(path)
    first, second = await asyncio.gather(connect(path), connect(path))
    try:
        for connection in (first, second):
            timeout = await (await connection.execute("PRAGMA busy_timeout")).fetchone()
            journal_limit = await (
                await connection.execute("PRAGMA journal_size_limit")
            ).fetchone()
            assert timeout[0] == 5000
            assert journal_limit[0] == 4_194_304
    finally:
        await asyncio.gather(first.close(), second.close())


@pytest.mark.parametrize(
    ("route", "mode", "status"),
    [
        ("primary", "normal", 200),
        ("primary", "429", 429),
        ("primary", "500", 500),
        ("secondary", "slow", 200),
    ],
)
@pytest.mark.asyncio
async def test_mock_provider_modes(route, mode, status) -> None:
    import httpx

    transport = httpx.ASGITransport(app=provider_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://provider") as client:
        response = await client.post(
            f"/{route}/v1/completions?mode={mode}", json={"prompt": "hello"}
        )
    assert response.status_code == status
    if status == 200:
        assert response.json()["provider"] == route
