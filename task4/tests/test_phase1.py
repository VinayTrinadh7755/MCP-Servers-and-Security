from __future__ import annotations

import re

import httpx
import pytest
import pytest_asyncio

from task4.app import app
from task4.limiter import TokenLimiter
from task4.router import CompletionRequest, ModelRouter


@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TASK4_DATABASE_PATH", str(tmp_path / "usage.db"))
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as value:
            yield value


@pytest.mark.asyncio
async def test_contracts_expose_required_phase1_fields() -> None:
    decision = await TokenLimiter().try_reserve("tenant-a", 100)
    result = await ModelRouter().complete(CompletionRequest("hello", 50))
    assert decision.allowed is True
    assert (decision.current_usage, decision.limit, decision.retry_after_seconds) == (
        0,
        50_000,
        None,
    )
    assert result.provider == "primary"
    assert result.failed_over is False


@pytest.mark.asyncio
async def test_completion_uses_primary_and_stable_success_shape(client) -> None:
    response = await client.post(
        "/v1/completions",
        headers={"x-tenant-key": "tenant-a"},
        json={"prompt": "hello", "max_tokens": 50},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "primary"
    assert body["failed_over"] is False
    assert body["request_id"] == response.headers["x-request-id"]


@pytest.mark.parametrize(
    ("headers", "content", "code"),
    [
        ({}, b"{}", "MISSING_TENANT_KEY"),
        ({"x-tenant-key": "tenant-a"}, b"{", "INVALID_JSON"),
        ({"x-tenant-key": "tenant-a"}, b"[]", "INVALID_REQUEST"),
        (
            {"x-tenant-key": "tenant-a"},
            b'{"prompt":"","max_tokens":true}',
            "INVALID_REQUEST",
        ),
    ],
)
@pytest.mark.asyncio
async def test_all_client_failures_use_gateway_error_envelope(
    client, headers, content, code
) -> None:
    response = await client.post("/v1/completions", headers=headers, content=content)
    error = response.json()["error"]
    assert error["code"] == code
    assert re.fullmatch(r"[0-9a-f]{32}", error["request_id"])
    assert response.headers["x-request-id"] == error["request_id"]
    serialized = response.text.casefold()
    for forbidden in ("traceback", "httpx", "sqlite3", 'file \\"'):
        assert forbidden not in serialized
