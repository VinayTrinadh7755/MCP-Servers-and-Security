import json
import logging
import os
import sys
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("task2.downstream")

app = FastAPI(title="Task 2 Mock MCP Downstream")

TOOLS = [
    {"name": "get_customer_record", "description": "Get a customer record", "inputSchema": {"type": "object"}},
    {"name": "search_orders", "description": "Search customer orders", "inputSchema": {"type": "object"}},
    {"name": "admin_reset_key", "description": "Reset an API key", "inputSchema": {"type": "object"}},
    {"name": "admin_delete_tenant", "description": "Delete a tenant", "inputSchema": {"type": "object"}},
]


def error_response(request_id: Any, code: int, message: str) -> JSONResponse:
    return JSONResponse(
        {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
    )


def audit_request(request_id: Any, method: Any, tool_name: Any) -> None:
    logger.info(
        "event=downstream_request id=%r method=%r tool=%r",
        request_id,
        method,
        tool_name,
    )
    audit_path = os.getenv("TASK2_DOWNSTREAM_AUDIT_FILE")
    if audit_path:
        with open(audit_path, "a", encoding="utf-8") as audit_file:
            audit_file.write(
                json.dumps(
                    {"id": request_id, "method": method, "tool": tool_name},
                    ensure_ascii=True,
                    separators=(",", ":"),
                )
                + "\n"
            )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "downstream"}


@app.post("/mcp")
async def mcp(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        logger.info("event=downstream_request outcome=parse_error")
        return error_response(None, -32700, "Parse error")

    if not isinstance(payload, dict):
        logger.info("event=downstream_request outcome=invalid_request")
        return error_response(None, -32600, "Invalid Request")

    request_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params")
    tool_name = params.get("name") if isinstance(params, dict) else None
    audit_request(request_id, method, tool_name)

    if payload.get("jsonrpc") != "2.0" or not isinstance(method, str):
        return error_response(request_id, -32600, "Invalid Request")
    if method == "tools/list":
        return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}})
    if method == "tools/call":
        name = tool_name
        if not isinstance(name, str):
            return error_response(request_id, -32602, "Invalid params")
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"content": [{"type": "text", "text": f"Executed {name}"}]},
            }
        )
    return error_response(request_id, -32601, "Method not found")
