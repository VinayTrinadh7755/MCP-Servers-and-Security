"""Prove that every server stdout line is an MCP JSON-RPC message."""

import json

from task1.tests.protocol import RawMCPClient


def test_stdout_contains_only_json_rpc_messages() -> None:
    with RawMCPClient() as client:
        client.request("tools/list")
        client.request(
            "tools/call",
            {
                "name": "trigger_refund",
                "arguments": {
                    "customer_id": "CUST-12345",
                    "amount": "50.00",
                    "reason": "duplicate charge",
                },
            },
        )
        client.request(
            "tools/call",
            {
                "name": "get_customer_record",
                "arguments": {"customer_id": "CUST-99999"},
            },
        )

    assert client.stdout_lines
    for line in client.stdout_lines:
        message = json.loads(line)
        assert message["jsonrpc"] == "2.0"
    assert "Traceback" not in client.stderr
