from __future__ import annotations

import logging
import sqlite3
import asyncio

import httpx
import pytest
import pytest_asyncio

from task4.app import app
from task4.router import ProviderFailure


class FailedRouter:
    async def complete(self, request):
        raise ProviderFailure("httpx.ConnectError provider.internal /srv/secret.py")


@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TASK4_DATABASE_PATH", str(tmp_path / "usage.db"))
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as value:
            yield value


@pytest.mark.asyncio
async def test_provider_failure_releases_reservation_and_leaks_nothing(client, caplog) -> None:
    app.state.router = FailedRouter()
    with caplog.at_level(logging.ERROR, logger="task4.gateway"):
        response = await client.post(
            "/v1/completions",
            headers={"x-tenant-key": "tenant-a"},
            json={"prompt": "hello", "max_tokens": 10},
        )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"
    body = response.text.casefold()
    for forbidden in ("provider.internal", "secret.py", "httpx", "traceback", "providerfailure"):
        assert forbidden not in body
    assert "request_id" in response.json()["error"]


@pytest.mark.asyncio
async def test_rate_limit_headers_and_reconciled_usage(client) -> None:
    class SuccessRouter:
        async def complete(self, request):
            from task4.router import CompletionResult

            return CompletionResult("primary", "ok", 2, 3, False)

    app.state.router = SuccessRouter()
    app.state.limiter.limit = 10
    first = await client.post(
        "/v1/completions",
        headers={"x-tenant-key": "tenant-a"},
        json={"prompt": "a", "max_tokens": 4},
    )
    assert first.status_code == 200
    assert first.headers["x-ratelimit-limit-tokens"] == "10"
    assert first.headers["x-ratelimit-remaining-tokens"] == "5"
    denied = await client.post(
        "/v1/completions",
        headers={"x-tenant-key": "tenant-a"},
        json={"prompt": "a", "max_tokens": 6},
    )
    assert denied.status_code == 429
    assert int(denied.headers["retry-after"]) >= 1
    assert denied.json()["error"]["code"] == "RATE_LIMITED"


@pytest.mark.asyncio
async def test_database_failure_and_oversized_inputs_use_sanitized_errors(client) -> None:
    too_long = await client.post(
        "/v1/completions",
        headers={"x-tenant-key": "x" * 257},
        json={"prompt": "hello", "max_tokens": 1},
    )
    assert too_long.status_code == 401
    assert too_long.json()["error"]["code"] == "MISSING_TENANT_KEY"

    too_large = await client.post(
        "/v1/completions",
        headers={"x-tenant-key": "tenant-a"},
        content=b"x" * 65_537,
    )
    assert too_large.status_code == 413
    assert too_large.json()["error"]["code"] == "INVALID_REQUEST"

    class BrokenLimiter:
        async def try_reserve(self, tenant_key, estimated_tokens):
            raise sqlite3.OperationalError("database is locked at C:/private/usage.db")

    app.state.limiter = BrokenLimiter()
    failed = await client.post(
        "/v1/completions",
        headers={"x-tenant-key": "tenant-a"},
        json={"prompt": "hello", "max_tokens": 1},
    )
    assert failed.status_code == 500
    assert failed.json()["error"]["code"] == "INTERNAL_ERROR"
    serialized = failed.text.casefold()
    for forbidden in ("sqlite3", "operationalerror", "private", "usage.db", "locked"):
        assert forbidden not in serialized


@pytest.mark.asyncio
async def test_omitted_max_tokens_reserves_safe_default(client) -> None:
    class FourThousandTokenRouter:
        async def complete(self, request):
            from task4.router import CompletionResult

            assert request.max_tokens == 4_096
            return CompletionResult("primary", "ok", 1, 4_000, False)

    app.state.router = FourThousandTokenRouter()
    app.state.limiter.limit = 50_000
    admitted_actual = 0
    statuses = []
    for _ in range(30):
        response = await client.post(
            "/v1/completions",
            headers={"x-tenant-key": "omitted-default"},
            json={"prompt": "hello"},
        )
        statuses.append(response.status_code)
        if response.status_code == 200:
            admitted_actual += 4_001
    assert statuses.count(200) == 12
    assert statuses.count(429) == 18
    assert admitted_actual == 48_012
    assert admitted_actual <= 50_000


@pytest.mark.asyncio
async def test_tenant_key_boundaries_and_parameterization(client) -> None:
    class SuccessRouter:
        async def complete(self, request):
            from task4.router import CompletionResult

            return CompletionResult("primary", "ok", 1, 1, False)

    app.state.router = SuccessRouter()
    cases = [
        ("", 401),
        ("   ", 401),
        ("x" * 10_000, 401),
        ("bad\x00key", 401),
        ("'; DROP TABLE token_usage;--", 200),
        ("tenant-a", 200),
        ("TENANT-A", 200),
    ]
    for key, expected in cases:
        response = await client.post(
            "/v1/completions",
            headers={"x-tenant-key": key},
            json={"prompt": "hello", "max_tokens": 1},
        )
        assert response.status_code == expected


@pytest.mark.asyncio
async def test_client_cancellation_releases_reservation(client) -> None:
    started = asyncio.Event()

    class HangingRouter:
        async def complete(self, request):
            started.set()
            await asyncio.Event().wait()

    app.state.router = HangingRouter()
    call = asyncio.create_task(
        client.post(
            "/v1/completions",
            headers={"x-tenant-key": "disconnecting-client"},
            json={"prompt": "hello", "max_tokens": 100},
        )
    )
    await asyncio.wait_for(started.wait(), timeout=1)
    call.cancel()
    with pytest.raises(asyncio.CancelledError):
        await call
    connection = sqlite3.connect(app.state.limiter.path)
    try:
        count = connection.execute(
            "SELECT COUNT(*) FROM token_usage WHERE tenant_key = ?",
            ("disconnecting-client",),
        ).fetchone()[0]
    finally:
        connection.close()
    assert count == 0
