from __future__ import annotations

import logging
import sqlite3

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
