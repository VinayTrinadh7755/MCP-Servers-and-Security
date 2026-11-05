import json

import httpx
import pytest

from task2.gateway.app import DEFAULT_MAX_BODY_BYTES, app
from task2.tests.test_proxy import RecordingUpstream


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name",
    [
        "admin_",
        "ADMIN_RESET_KEY",
        "Admin_Reset_Key",
        " admin_reset_key",
        "аdmin_reset_key",  # First character is Cyrillic.
        "",
        [],
        {},
    ],
)
async def test_hostile_tool_names_are_blocked_without_forwarding(name: object) -> None:
    upstream = RecordingUpstream()
    app.state.upstream = upstream
    request = {
        "jsonrpc": "2.0",
        "id": "hostile",
        "method": "tools/call",
        "params": {"name": name, "arguments": {}},
    }

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://gateway"
    ) as client:
        response = await client.post(
            "/mcp",
            json=request,
            headers={"authorization": "Bearer token-viewer-001"},
        )

    assert response.json()["error"]["code"] == -32001
    assert response.json()["id"] == "hostile"
    assert upstream.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("params", [None, {}, {"arguments": {}}])
async def test_missing_name_or_params_are_blocked_without_forwarding(params: object) -> None:
    upstream = RecordingUpstream()
    app.state.upstream = upstream
    request = {"jsonrpc": "2.0", "id": 4, "method": "tools/call"}
    if params is not None:
        request["params"] = params

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://gateway"
    ) as client:
        response = await client.post("/mcp", json=request)

    assert response.json()["error"]["code"] == -32001
    assert upstream.calls == []


@pytest.mark.asyncio
async def test_duplicate_name_key_is_rejected_without_forwarding() -> None:
    upstream = RecordingUpstream()
    app.state.upstream = upstream
    body = (
        b'{"jsonrpc":"2.0","id":5,"method":"tools/call","params":'
        b'{"name":"search_orders","name":"admin_reset_key","arguments":{}}}'
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://gateway"
    ) as client:
        response = await client.post(
            "/mcp", content=body, headers={"content-type": "application/json"}
        )

    assert response.json()["error"]["code"] == -32600
    assert upstream.calls == []


@pytest.mark.asyncio
async def test_duplicate_authorization_headers_cannot_supply_admin_role() -> None:
    upstream = RecordingUpstream()
    app.state.upstream = upstream
    request = {
        "jsonrpc": "2.0",
        "id": 6,
        "method": "tools/call",
        "params": {"name": "admin_reset_key", "arguments": {}},
    }
    headers = [
        ("authorization", "Bearer token-admin-001"),
        ("authorization", "Bearer token-viewer-001"),
    ]

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://gateway"
    ) as client:
        response = await client.post("/mcp", json=request, headers=headers)

    assert response.json()["error"]["code"] == -32001
    assert upstream.calls == []


@pytest.mark.asyncio
async def test_oversized_body_is_rejected_before_parsing_or_forwarding() -> None:
    upstream = RecordingUpstream()
    app.state.upstream = upstream
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/list",
            "padding": "x" * DEFAULT_MAX_BODY_BYTES,
        }
    ).encode()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://gateway"
    ) as client:
        response = await client.post(
            "/mcp", content=body, headers={"content-type": "application/json"}
        )

    assert response.json() == {
        "jsonrpc": "2.0",
        "id": None,
        "error": {"code": -32600, "message": "Invalid Request"},
    }
    assert upstream.calls == []


@pytest.mark.asyncio
async def test_similar_non_privileged_name_remains_allowed() -> None:
    upstream = RecordingUpstream()
    app.state.upstream = upstream
    request = {
        "jsonrpc": "2.0",
        "id": 8,
        "method": "tools/call",
        "params": {"name": "administrator_reset", "arguments": {}},
    }

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://gateway"
    ) as client:
        response = await client.post("/mcp", json=request)

    assert response.json()["result"]["forwarded"] is True
    assert len(upstream.calls) == 1


@pytest.mark.asyncio
async def test_json_unicode_escape_decodes_then_privileged_prefix_is_blocked() -> None:
    upstream = RecordingUpstream()
    app.state.upstream = upstream
    body = (
        b'{"jsonrpc":"2.0","id":9,"method":"tools/call","params":'
        b'{"name":"\\u0061dmin_reset_key","arguments":{}}}'
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://gateway"
    ) as client:
        response = await client.post(
            "/mcp", content=body, headers={"content-type": "application/json"}
        )

    assert response.json()["error"]["code"] == -32001
    assert upstream.calls == []
