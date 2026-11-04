import json

import httpx
import pytest

from task2.gateway.app import app
from task2.gateway.upstream import UpstreamFailure


class RecordingUpstream:
    def __init__(self) -> None:
        self.calls: list[tuple[bytes, str]] = []

    async def forward(self, body: bytes, content_type: str) -> dict:
        self.calls.append((body, content_type))
        request = json.loads(body)
        return {"jsonrpc": "2.0", "id": request["id"], "result": {"forwarded": True}}


class FailingUpstream:
    async def forward(self, body: bytes, content_type: str) -> dict:
        raise UpstreamFailure


@pytest.mark.asyncio
async def test_forwards_raw_request_and_preserves_zero_id() -> None:
    upstream = RecordingUpstream()
    app.state.upstream = upstream
    body = b'{"jsonrpc":"2.0","id":0,"method":"tools/list"}'

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://gateway"
    ) as client:
        response = await client.post("/mcp", content=body, headers={"content-type": "application/json"})

    assert response.json() == {"jsonrpc": "2.0", "id": 0, "result": {"forwarded": True}}
    assert upstream.calls == [(body, "application/json")]


@pytest.mark.asyncio
async def test_sanitizes_upstream_failure_and_preserves_string_id() -> None:
    app.state.upstream = FailingUpstream()
    body = {"jsonrpc": "2.0", "id": "request-7", "method": "tools/list"}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://gateway"
    ) as client:
        response = await client.post("/mcp", json=body)

    serialized = response.text
    assert response.json() == {
        "jsonrpc": "2.0",
        "id": "request-7",
        "error": {"code": -32603, "message": "Downstream service unavailable"},
    }
    assert "httpx" not in serialized
    assert "Traceback" not in serialized


@pytest.mark.asyncio
async def test_rejects_malformed_and_batch_requests_without_forwarding() -> None:
    upstream = RecordingUpstream()
    app.state.upstream = upstream

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://gateway"
    ) as client:
        malformed = await client.post("/mcp", content=b"{bad")
        batch = await client.post(
            "/mcp", json=[{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}]
        )

    assert malformed.json()["error"]["code"] == -32700
    assert batch.json()["error"]["code"] == -32600
    assert upstream.calls == []
