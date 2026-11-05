import logging

import httpx
import pytest

from task2.gateway.app import app
from task2.tests.test_proxy import FailingUpstream, RecordingUpstream


@pytest.mark.asyncio
async def test_parse_failure_has_correlated_diagnostic_log(caplog: pytest.LogCaptureFixture) -> None:
    app.state.upstream = RecordingUpstream()
    caplog.set_level(logging.INFO, logger="task2.gateway")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://gateway"
    ) as client:
        response = await client.post(
            "/mcp", content=b"{bad", headers={"content-type": "application/json"}
        )

    correlation_id = response.headers["x-request-id"]
    assert response.json()["error"]["code"] == -32700
    assert correlation_id in caplog.text
    assert "reason=parse_error" in caplog.text


@pytest.mark.asyncio
async def test_policy_denial_log_has_correlation_and_no_token(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app.state.upstream = RecordingUpstream()
    caplog.set_level(logging.INFO, logger="task2.gateway")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://gateway"
    ) as client:
        response = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": "denied-log",
                "method": "tools/call",
                "params": {"name": "admin_reset_key", "arguments": {}},
            },
            headers={"authorization": "Bearer token-viewer-001"},
        )

    correlation_id = response.headers["x-request-id"]
    assert correlation_id in caplog.text
    assert "rpc_id='denied-log'" in caplog.text
    assert "token-viewer-001" not in caplog.text


@pytest.mark.asyncio
async def test_upstream_failure_log_has_correlation_and_detail(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app.state.upstream = FailingUpstream()
    caplog.set_level(logging.INFO, logger="task2.gateway")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://gateway"
    ) as client:
        response = await client.post(
            "/mcp", json={"jsonrpc": "2.0", "id": "failed-upstream", "method": "tools/list"}
        )

    correlation_id = response.headers["x-request-id"]
    assert correlation_id in caplog.text
    assert "rpc_id='failed-upstream'" in caplog.text
    assert "upstream_failure" in caplog.text
