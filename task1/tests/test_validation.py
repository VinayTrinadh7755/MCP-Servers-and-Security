"""Raw protocol tests for strict validation and business-result separation."""

import pytest

from task1.tests.protocol import RawMCPClient


INVALID_REFUNDS = [
    {"customer_id": "CUST-1234", "amount": 1.0, "reason": "duplicate charge"},
    {
        "customer_id": "CUST-12345\nCUST-99999",
        "amount": 1.0,
        "reason": "duplicate charge",
    },
    {"customer_id": "CUST-١٢٣٤٥", "amount": 1.0, "reason": "duplicate charge"},
    {"customer_id": "CUST-12345", "amount": 0.0, "reason": "duplicate charge"},
    {"customer_id": "CUST-12345", "amount": "50.00", "reason": "duplicate charge"},
    {"customer_id": "CUST-12345", "amount": 1.0, "reason": "123456789"},
    {"customer_id": "CUST-12345", "amount": 1.0, "reason": "x" * 1001},
    {
        "customer_id": "CUST-12345",
        "amount": 1.0,
        "reason": "duplicate charge",
        "is_admin": True,
    },
    {},
]


@pytest.mark.parametrize("arguments", INVALID_REFUNDS)
def test_invalid_refund_arguments_return_invalid_params(arguments: dict) -> None:
    with RawMCPClient() as client:
        response = client.request(
            "tools/call",
            {"name": "trigger_refund", "arguments": arguments},
            request_id=0,
        )

    assert response["id"] == 0
    assert response["error"]["code"] == -32602
    assert response["error"]["message"] == "Invalid params"
    serialized = str(response["error"].get("data", ""))
    assert "pydantic_core" not in serialized
    assert "Traceback" not in serialized
    assert 'File "' not in serialized
    assert "http://" not in serialized
    assert "https://" not in serialized


def test_unknown_tool_returns_method_not_found() -> None:
    with RawMCPClient() as client:
        response = client.request(
            "tools/call",
            {"name": "does_not_exist", "arguments": {}},
        )

    assert response["error"]["code"] == -32601


def test_business_failure_is_tool_result_not_protocol_error() -> None:
    with RawMCPClient() as client:
        response = client.request(
            "tools/call",
            {
                "name": "get_customer_record",
                "arguments": {"customer_id": "CUST-99999"},
            },
        )

    assert "error" not in response
    assert response["result"]["isError"] is True
    assert "not found" in response["result"]["content"][0]["text"]


def test_over_balance_refund_is_business_failure() -> None:
    with RawMCPClient() as client:
        response = client.request(
            "tools/call",
            {
                "name": "trigger_refund",
                "arguments": {
                    "customer_id": "CUST-23456",
                    "amount": 50.01,
                    "reason": "duplicate charge",
                },
            },
        )

    assert "error" not in response
    assert response["result"]["isError"] is True
    assert "exceeds" in response["result"]["content"][0]["text"]


def test_session_survives_validation_error() -> None:
    with RawMCPClient() as client:
        invalid = client.request(
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
        valid = client.request(
            "tools/call",
            {
                "name": "get_customer_record",
                "arguments": {"customer_id": "CUST-12345"},
            },
        )

    assert invalid["error"]["code"] == -32602
    assert valid["result"]["isError"] is False
