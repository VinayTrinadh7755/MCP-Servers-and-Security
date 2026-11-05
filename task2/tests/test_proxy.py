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
        malformed = await client.post(
            "/mcp", content=b"{bad", headers={"content-type": "application/json"}
        )
        batch = await client.post(
            "/mcp",
            json=[
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "search_orders", "arguments": {}},
                },
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "admin_reset_key", "arguments": {}},
                },
            ],
        )

    assert malformed.json()["error"]["code"] == -32700
    assert batch.json()["error"]["code"] == -32600
    assert upstream.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("authorization", [None, "Bearer token-viewer-001", "Bearer unknown"])
async def test_blocks_privileged_call_before_forwarding(authorization: str | None) -> None:
    upstream = RecordingUpstream()
    app.state.upstream = upstream
    headers = {"authorization": authorization} if authorization else {}
    body = {
        "jsonrpc": "2.0",
        "id": "blocked-1",
        "method": "tools/call",
        "params": {"name": "admin_reset_key", "arguments": {}},
    }

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://gateway"
    ) as client:
        response = await client.post("/mcp", json=body, headers=headers)

    assert response.json() == {
        "jsonrpc": "2.0",
        "id": "blocked-1",
        "error": {"code": -32001, "message": "Unauthorized Tool Call"},
    }
    assert upstream.calls == []


@pytest.mark.asyncio
async def test_admin_privileged_call_reaches_downstream() -> None:
    upstream = RecordingUpstream()
    app.state.upstream = upstream
    body = {
        "jsonrpc": "2.0",
        "id": 9,
        "method": "tools/call",
        "params": {"name": "admin_delete_tenant", "arguments": {}},
    }

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://gateway"
    ) as client:
        response = await client.post(
            "/mcp", json=body, headers={"authorization": "Bearer token-admin-001"}
        )

    assert response.json()["id"] == 9
    assert len(upstream.calls) == 1


@pytest.mark.asyncio
async def test_unknown_method_fails_closed_without_forwarding() -> None:
    upstream = RecordingUpstream()
    app.state.upstream = upstream

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://gateway"
    ) as client:
        response = await client.post(
            "/mcp", json={"jsonrpc": "2.0", "id": 10, "method": "resources/list"}
        )

    assert response.json() == {
        "jsonrpc": "2.0",
        "id": 10,
        "error": {"code": -32601, "message": "Method not found"},
    }
    assert upstream.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_id", [{"nested": 1}, [1, 2], True])
async def test_rejects_non_json_rpc_id_types_without_forwarding(bad_id: object) -> None:
    upstream = RecordingUpstream()
    app.state.upstream = upstream

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://gateway"
    ) as client:
        response = await client.post(
            "/mcp", json={"jsonrpc": "2.0", "id": bad_id, "method": "tools/list"}
        )

    assert response.json()["error"]["code"] == -32600
    assert response.json()["id"] is None
    assert upstream.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("content_type", [None, "text/plain"])
async def test_requires_json_content_type(content_type: str | None) -> None:
    upstream = RecordingUpstream()
    app.state.upstream = upstream
    headers = {"content-type": content_type} if content_type else {}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://gateway"
    ) as client:
        response = await client.post(
            "/mcp",
            content=b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}',
            headers=headers,
        )

    assert response.json()["error"]["code"] == -32600
    assert upstream.calls == []


@pytest.mark.asyncio
async def test_concurrent_responses_keep_ids_and_denies_off_upstream() -> None:
    upstream = RecordingUpstream()
    app.state.upstream = upstream

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://gateway"
    ) as client:
        async def send(index: int) -> tuple[str, int, object]:
            allowed = index % 2 == 0
            request_id = f"request-{index}"
            response = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": "tools/call",
                    "params": {
                        "name": "search_orders" if allowed else "admin_reset_key",
                        "arguments": {},
                    },
                },
                headers={"authorization": "Bearer token-viewer-001"},
            )
            body = response.json()
            return request_id, response.status_code, body["id"]

        import asyncio

        results = await asyncio.gather(*(send(index) for index in range(100)))

    assert all(expected == actual for expected, _, actual in results)
    assert all(status == 200 for _, status, _ in results)
    assert len(upstream.calls) == 50
