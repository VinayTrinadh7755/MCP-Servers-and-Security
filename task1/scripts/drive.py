"""Launch the Task 1 server and verify the initial empty tool contract."""

from __future__ import annotations

import asyncio
import argparse
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.exceptions import McpError


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SERVER_PATH = PROJECT_ROOT / "task1" / "server.py"


def result_text(result: object) -> str:
    content = getattr(result, "content", [])
    return content[0].text if content else "<no content>"


async def main(dump_schema: bool, validate: bool, scenario: str | None) -> None:
    server = StdioServerParameters(command=sys.executable, args=[str(SERVER_PATH)])

    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.list_tools()
            print([tool.name for tool in result.tools])

            if dump_schema:
                schemas = {tool.name: tool.inputSchema for tool in result.tools}
                print(json.dumps(schemas, indent=2, sort_keys=True))
                return

            if validate:
                cases = [
                    (
                        "reason_exactly_10",
                        {"customer_id": "CUST-12345", "amount": 0.01, "reason": "0123456789"},
                    ),
                    (
                        "reason_9",
                        {"customer_id": "CUST-12345", "amount": 0.01, "reason": "012345678"},
                    ),
                    (
                        "zero_amount",
                        {"customer_id": "CUST-12345", "amount": 0.0, "reason": "duplicate charge"},
                    ),
                    (
                        "string_amount",
                        {"customer_id": "CUST-12345", "amount": "50.00", "reason": "duplicate charge"},
                    ),
                    (
                        "extra_field",
                        {
                            "customer_id": "CUST-12345",
                            "amount": 10.5,
                            "reason": "duplicate charge",
                            "is_admin": True,
                        },
                    ),
                    (
                        "embedded_newline",
                        {
                            "customer_id": "CUST-12345\nCUST-99999",
                            "amount": 10.5,
                            "reason": "duplicate charge",
                        },
                    ),
                    (
                        "reason_10000",
                        {
                            "customer_id": "CUST-12345",
                            "amount": 10.5,
                            "reason": "x" * 10_000,
                        },
                    ),
                ]
                for case_name, arguments in cases:
                    try:
                        call = await session.call_tool("trigger_refund", arguments)
                        print(f"{case_name} isError={call.isError}")
                    except McpError as exc:
                        print(f"{case_name} error_code={exc.error.code}")
                return

            if scenario == "all":
                scenarios = [
                    (
                        "known_customer",
                        "get_customer_record",
                        {"customer_id": "CUST-12345"},
                    ),
                    (
                        "unknown_customer",
                        "get_customer_record",
                        {"customer_id": "CUST-99999"},
                    ),
                    (
                        "refund_over_balance",
                        "trigger_refund",
                        {
                            "customer_id": "CUST-23456",
                            "amount": 50.01,
                            "reason": "duplicate charge",
                        },
                    ),
                    (
                        "valid_refund",
                        "trigger_refund",
                        {
                            "customer_id": "CUST-12345",
                            "amount": 10.5,
                            "reason": "duplicate charge",
                        },
                    ),
                    (
                        "refund_exact_balance",
                        "trigger_refund",
                        {
                            "customer_id": "CUST-23456",
                            "amount": 50.0,
                            "reason": "account closure refund",
                        },
                    ),
                    (
                        "refund_one_cent_over",
                        "trigger_refund",
                        {
                            "customer_id": "CUST-34567",
                            "amount": 25.01,
                            "reason": "duplicate charge",
                        },
                    ),
                ]
                for label, tool_name, arguments in scenarios:
                    call = await session.call_tool(tool_name, arguments)
                    print(
                        f"{label} isError={call.isError} "
                        f"content={result_text(call)}"
                    )
                return

            customer = await session.call_tool(
                "get_customer_record",
                {"customer_id": "CUST-12345"},
            )
            refund = await session.call_tool(
                "trigger_refund",
                {
                    "customer_id": "CUST-12345",
                    "amount": 10.5,
                    "reason": "duplicate charge",
                },
            )
            print(f"get_customer_record isError={customer.isError}")
            print(f"trigger_refund isError={refund.isError}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dump-schema", action="store_true")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--scenario", choices=["all"])
    args = parser.parse_args()
    asyncio.run(main(args.dump_schema, args.validate, args.scenario))
