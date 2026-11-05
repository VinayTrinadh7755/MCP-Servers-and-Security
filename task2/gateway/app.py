import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from task2.gateway.auth import resolve_identity
from task2.gateway.policy import authorize
from task2.gateway.upstream import UpstreamClient, UpstreamFailure


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("task2.gateway")
DEFAULT_MAX_BODY_BYTES = 65_536


class BodyTooLarge(Exception):
    pass


class DuplicateKey(Exception):
    pass


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKey(key)
        result[key] = value
    return result


async def read_limited_body(request: Request, limit: int) -> bytes:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > limit or int(content_length) < 0:
                raise BodyTooLarge
        except ValueError as exc:
            raise BodyTooLarge from exc

    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > limit:
            raise BodyTooLarge
        body.extend(chunk)
    return bytes(body)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    downstream_url = os.getenv("TASK2_DOWNSTREAM_URL", "http://127.0.0.1:8001")
    app.state.max_body_bytes = int(
        os.getenv("TASK2_MAX_BODY_BYTES", str(DEFAULT_MAX_BODY_BYTES))
    )
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
    try:
        body = await read_limited_body(
            request,
            getattr(request.app.state, "max_body_bytes", DEFAULT_MAX_BODY_BYTES),
        )
    except BodyTooLarge:
        return error_response(None, -32600, "Invalid Request")

    try:
        payload = json.loads(body, object_pairs_hook=reject_duplicate_keys)
    except DuplicateKey:
        return error_response(None, -32600, "Invalid Request")
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return error_response(None, -32700, "Parse error")

    if not isinstance(payload, dict):
        return error_response(None, -32600, "Invalid Request")

    request_id = payload.get("id")
    if payload.get("jsonrpc") != "2.0" or not isinstance(payload.get("method"), str):
        return error_response(request_id, -32600, "Invalid Request")

    authorization_headers = request.headers.getlist("authorization")
    identity = resolve_identity(
        authorization_headers[0] if len(authorization_headers) == 1 else None
    )
    decision = authorize(
        payload["method"],
        payload.get("params"),
        identity.role if identity else None,
    )
    logger.info(
        "event=authorization subject=%s role=%s method=%s tool=%s outcome=%s reason=%s",
        identity.subject if identity else "anonymous",
        identity.role if identity else "none",
        payload["method"],
        decision.tool_name,
        "allow" if decision.allowed else "deny",
        decision.reason,
    )
    if not decision.allowed:
        return error_response(request_id, -32001, "Unauthorized Tool Call")

    try:
        response_payload = await request.app.state.upstream.forward(
            body,
            request.headers.get("content-type", "application/json"),
        )
    except UpstreamFailure:
        logger.exception("event=forward outcome=upstream_failure id=%r", request_id)
        return error_response(request_id, -32603, "Downstream service unavailable")

    return JSONResponse(response_payload)
