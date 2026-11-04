import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from task2.gateway.upstream import UpstreamClient, UpstreamFailure


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("task2.gateway")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    downstream_url = os.getenv("TASK2_DOWNSTREAM_URL", "http://127.0.0.1:8001")
    app.state.upstream = UpstreamClient(downstream_url)
    try:
        yield
    finally:
        await app.state.upstream.close()


app = FastAPI(title="Task 2 MCP Security Gateway", lifespan=lifespan)


def error_response(request_id: Any, code: int, message: str) -> JSONResponse:
    return JSONResponse(
        {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "gateway"}


@app.post("/mcp")
async def mcp(request: Request) -> JSONResponse:
    body = await request.body()
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return error_response(None, -32700, "Parse error")

    if not isinstance(payload, dict):
        return error_response(None, -32600, "Invalid Request")

    request_id = payload.get("id")
    if payload.get("jsonrpc") != "2.0" or not isinstance(payload.get("method"), str):
        return error_response(request_id, -32600, "Invalid Request")

    try:
        response_payload = await request.app.state.upstream.forward(
            body,
            request.headers.get("content-type", "application/json"),
        )
    except UpstreamFailure:
        logger.exception("event=forward outcome=upstream_failure id=%r", request_id)
        return error_response(request_id, -32603, "Downstream service unavailable")

    return JSONResponse(response_payload)
