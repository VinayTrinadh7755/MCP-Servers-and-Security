"""Task 4 completion gateway, with Phase 1 stub collaborators."""

from __future__ import annotations

import json
import logging
import sys
import uuid
from contextlib import asynccontextmanager
from json import JSONDecodeError
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from task4.db.connection import init
from task4.errors import error_response
from task4.limiter import TokenLimiter
from task4.router import CompletionRequest, ModelRouter


logger = logging.getLogger("task4.gateway")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
logger.propagate = False


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init()
    app.state.limiter = TokenLimiter()
    app.state.router = ModelRouter()
    yield


app = FastAPI(title="Task 4 Rate-Limit and Fallback Gateway", lifespan=lifespan)


def gateway_error(
    request_id: str, code: str, message: str, status_code: int
) -> JSONResponse:
    logger.warning("event=request_rejected request_id=%s code=%s", request_id, code)
    return error_response(
        code=code, message=message, request_id=request_id, status_code=status_code
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    del exc
    request_id = getattr(request.state, "request_id", uuid.uuid4().hex)
    return gateway_error(request_id, "INVALID_REQUEST", "Invalid request", 400)


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", uuid.uuid4().hex)
    logger.exception(
        "event=request_failed request_id=%s exception=%s", request_id, type(exc).__name__
    )
    return error_response(
        code="INTERNAL_ERROR",
        message="Gateway request failed",
        request_id=request_id,
        status_code=500,
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/completions")
async def completions(request: Request) -> JSONResponse:
    request_id = uuid.uuid4().hex
    request.state.request_id = request_id
    tenant_key = request.headers.get("x-tenant-key")
    if tenant_key is None or not tenant_key.strip():
        return gateway_error(
            request_id, "MISSING_TENANT_KEY", "x-tenant-key header is required", 401
        )

    try:
        payload = json.loads(await request.body())
    except (JSONDecodeError, UnicodeDecodeError):
        return gateway_error(request_id, "INVALID_JSON", "Request body must be valid JSON", 400)
    if not isinstance(payload, dict):
        return gateway_error(request_id, "INVALID_REQUEST", "Request body must be an object", 400)

    prompt = payload.get("prompt")
    max_tokens = payload.get("max_tokens")
    if (
        not isinstance(prompt, str)
        or not prompt
        or isinstance(max_tokens, bool)
        or not isinstance(max_tokens, int)
        or max_tokens <= 0
    ):
        return gateway_error(
            request_id,
            "INVALID_REQUEST",
            "prompt must be non-empty and max_tokens must be a positive integer",
            400,
        )

    estimated_tokens = len(prompt) // 4 + 1 + max_tokens
    decision = await request.app.state.limiter.try_reserve(
        tenant_key.strip(), estimated_tokens
    )
    if not decision.allowed:
        return gateway_error(request_id, "RATE_LIMITED", "Token limit exceeded", 429)

    result = await request.app.state.router.complete(CompletionRequest(prompt, max_tokens))
    await request.app.state.limiter.reconcile(
        decision.request_id, result.prompt_tokens + result.completion_tokens
    )
    return JSONResponse(
        {
            "request_id": request_id,
            "provider": result.provider,
            "text": result.text,
            "usage": {
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
            },
            "failed_over": result.failed_over,
        },
        headers={"x-request-id": request_id},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("task4.app:app", host="127.0.0.1", port=8200)
