import json
import logging
import os
import sys
import uuid
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
DEFAULT_MAX_RESPONSE_BYTES = 1_048_576


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
    app.state.upstream = UpstreamClient(
        downstream_url,
        read_timeout=float(os.getenv("TASK2_UPSTREAM_READ_TIMEOUT", "5.0")),
        max_response_bytes=int(
            os.getenv("TASK2_MAX_RESPONSE_BYTES", str(DEFAULT_MAX_RESPONSE_BYTES))
        ),
    )
    try:
        yield
    finally:
        await app.state.upstream.close()


app = FastAPI(title="Task 2 MCP Security Gateway", lifespan=lifespan)


def error_response(
    request_id: Any,
    code: int,
    message: str,
    correlation_id: str | None = None,
) -> JSONResponse:
    return JSONResponse(
        {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}},
        headers={"x-request-id": correlation_id} if correlation_id else None,
    )


def valid_request_id(value: Any) -> bool:
    return value is None or (
        isinstance(value, (str, int, float)) and not isinstance(value, bool)
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "gateway"}


@app.post("/mcp")
async def mcp(request: Request) -> JSONResponse:
    correlation_id = uuid.uuid4().hex
    content_type = request.headers.get("content-type")
    media_type = content_type.split(";", 1)[0].strip().casefold() if content_type else None
    if media_type != "application/json":
        logger.warning(
            "event=request_rejected request_id=%s rpc_id=None reason=unsupported_content_type",
            correlation_id,
        )
        return error_response(None, -32600, "Invalid Request", correlation_id)

    try:
        body = await read_limited_body(
            request,
            getattr(request.app.state, "max_body_bytes", DEFAULT_MAX_BODY_BYTES),
        )
    except BodyTooLarge:
        logger.warning(
            "event=request_rejected request_id=%s rpc_id=None reason=body_too_large",
            correlation_id,
        )
        return error_response(None, -32600, "Invalid Request", correlation_id)

    try:
        payload = json.loads(body, object_pairs_hook=reject_duplicate_keys)
    except DuplicateKey:
        logger.warning(
            "event=request_rejected request_id=%s rpc_id=None reason=duplicate_key",
            correlation_id,
        )
        return error_response(None, -32600, "Invalid Request", correlation_id)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        logger.warning(
            "event=request_rejected request_id=%s rpc_id=None reason=parse_error",
            correlation_id,
        )
        return error_response(None, -32700, "Parse error", correlation_id)

    if not isinstance(payload, dict):
        logger.warning(
            "event=request_rejected request_id=%s rpc_id=None reason=non_object",
            correlation_id,
        )
        return error_response(None, -32600, "Invalid Request", correlation_id)

    request_id = payload.get("id")
    if (
        payload.get("jsonrpc") != "2.0"
        or not isinstance(payload.get("method"), str)
        or not valid_request_id(request_id)
    ):
        response_id = request_id if valid_request_id(request_id) else None
        logger.warning(
            "event=request_rejected request_id=%s rpc_id=%r reason=invalid_envelope",
            correlation_id,
            response_id,
        )
        return error_response(response_id, -32600, "Invalid Request", correlation_id)

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
        "event=authorization request_id=%s rpc_id=%r subject=%s role=%s method=%s tool=%s outcome=%s reason=%s",
        correlation_id,
        request_id,
        identity.subject if identity else "anonymous",
        identity.role if identity else "none",
        payload["method"],
        decision.tool_name,
        "allow" if decision.allowed else "deny",
        decision.reason,
    )
    if not decision.allowed:
        if decision.reason == "unsupported_method":
            return error_response(request_id, -32601, "Method not found", correlation_id)
        return error_response(
            request_id, -32001, "Unauthorized Tool Call", correlation_id
        )

    try:
        response_payload = await request.app.state.upstream.forward(
            body,
            content_type,
        )
    except UpstreamFailure:
        logger.exception(
            "event=forward request_id=%s rpc_id=%r outcome=upstream_failure",
            correlation_id,
            request_id,
        )
        return error_response(
            request_id, -32603, "Downstream service unavailable", correlation_id
        )

    return JSONResponse(response_payload)
