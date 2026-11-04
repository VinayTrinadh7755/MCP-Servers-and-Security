"""Minimal Task 1 MCP server used to prove the stdio transport setup."""

from __future__ import annotations

import json
import logging
import os
import sys
from collections.abc import AsyncIterator
from decimal import Decimal
from io import TextIOWrapper
from typing import Any

import anyio
import mcp.types as types
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.stdio import stdio_server
from pydantic import ConfigDict, ValidationError

try:
    from task1.models import CustomerId, PositiveAmount, RefundReason
    from task1 import store
except ModuleNotFoundError:  # Direct execution: python task1/server.py
    from models import CustomerId, PositiveAmount, RefundReason
    import store


def configure_stderr_logging() -> None:
    """Keep application logs off stdout, which is reserved for MCP messages."""
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root_logger.addHandler(stderr_handler)
    root_logger.setLevel(logging.INFO)


configure_stderr_logging()
logger = logging.getLogger("task1.audit")
logger.handlers.clear()
audit_handler = logging.StreamHandler(sys.stderr)
audit_handler.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(audit_handler)
logger.setLevel(logging.INFO)
logger.propagate = False


class WhitespaceTolerantFastMCP(FastMCP):
    """Ignore empty stdio frames before the SDK parses JSON-RPC messages."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self._install_strict_call_handler()

    def _install_strict_call_handler(self) -> None:
        async def call_tool(req: types.CallToolRequest):
            tool = self._tool_manager.get_tool(req.params.name)
            if tool is None:
                return types.ErrorData(
                    code=types.METHOD_NOT_FOUND,
                    message="Unknown tool",
                )

            try:
                result = await tool.run(
                    req.params.arguments or {},
                    context=self.get_context(),
                    convert_result=True,
                )
            except ToolError as exc:
                if isinstance(exc.__cause__, ValidationError):
                    return types.ErrorData(
                        code=types.INVALID_PARAMS,
                        message="Invalid params",
                        data=exc.__cause__.errors(include_url=False),
                    )
                return types.ServerResult(
                    types.CallToolResult(
                        content=[types.TextContent(type="text", text=str(exc))],
                        isError=True,
                    )
                )

            if isinstance(result, types.CallToolResult):
                return types.ServerResult(result)

            return types.ServerResult(
                types.CallToolResult(content=list(result), isError=False)
            )

        self._mcp_server.request_handlers[types.CallToolRequest] = call_tool

    def add_tool(self, fn: Any, **kwargs: Any) -> None:
        """Apply the strict boundary policy to FastMCP's generated input model."""
        super().add_tool(fn, **kwargs)
        tool_name = kwargs.get("name") or fn.__name__
        tool = self._tool_manager.get_tool(tool_name)
        if tool is None:  # pragma: no cover - registration guarantees the tool
            raise RuntimeError(f"Tool registration failed: {tool_name}")

        tool.fn_metadata.arg_model.model_config = ConfigDict(
            extra="forbid",
            strict=True,
        )
        tool.fn_metadata.arg_model.model_rebuild(force=True)
        tool.parameters = tool.fn_metadata.arg_model.model_json_schema(by_alias=True)

    async def run_stdio_async(self) -> None:
        stdin = anyio.wrap_file(
            TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
        )

        async def nonblank_lines() -> AsyncIterator[str]:
            async for line in stdin:
                if line.strip():
                    yield line

        async with stdio_server(stdin=nonblank_lines()) as (read_stream, write_stream):  # type: ignore[arg-type]
            await self._mcp_server.run(
                read_stream,
                write_stream,
                self._mcp_server.create_initialization_options(),
            )


mcp = WhitespaceTolerantFastMCP("customer-operations")


@mcp.tool(structured_output=False)
def get_customer_record(customer_id: CustomerId) -> types.CallToolResult:
    """Return the record for a customer ID formatted as CUST- plus five ASCII digits."""
    if os.getenv("TASK1_TEST_STUB_ERROR") == "1":
        raise RuntimeError("deliberate stub failure")

    customer = store.get(customer_id)
    if customer is None:
        _audit("get_customer_record", customer_id, "not_found")
        return _tool_result(f"Customer {customer_id} was not found", is_error=True)

    # Audit metadata deliberately excludes the record and its email address.
    _audit("get_customer_record", customer_id, "found")
    return _tool_result(json.dumps(customer, sort_keys=True))


@mcp.tool(structured_output=False)
def trigger_refund(
    customer_id: CustomerId,
    amount: PositiveAmount,
    reason: RefundReason,
) -> types.CallToolResult:
    """Trigger a refund for a customer ID formatted as CUST- plus five ASCII digits."""
    customer = store.get(customer_id)
    if customer is None:
        _audit("trigger_refund", customer_id, "not_found")
        return _tool_result(f"Customer {customer_id} was not found", is_error=True)

    if Decimal(str(amount)) > Decimal(customer["balance"]):
        _audit("trigger_refund", customer_id, "insufficient_balance")
        return _tool_result(
            f"Refund amount exceeds the available balance of {customer['balance']}",
            is_error=True,
        )

    refund = store.record_refund(customer_id, amount, reason)
    _audit("trigger_refund", customer_id, "recorded")
    return _tool_result(json.dumps(refund, sort_keys=True))


def _tool_result(message: str, *, is_error: bool = False) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=message)],
        isError=is_error,
    )


def _audit(tool_name: str, customer_id: str, outcome: str) -> None:
    logger.info(
        json.dumps(
            {
                "event": "tool_call",
                "tool": tool_name,
                "customer_id": customer_id,
                "outcome": outcome,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    # Test-only fault injection proves the stdout-purity test detects contamination.
    if os.getenv("MCP_SELFTEST") == "1":
        os.write(1, b"MCP_SELFTEST_STDOUT_CONTAMINATION\n")
    mcp.run(transport="stdio")
