"""Task 4 completion gateway, with Phase 1 stub collaborators."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import uuid
from contextlib import asynccontextmanager
from json import JSONDecodeError
from typing import AsyncIterator

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from task4.db.connection import init
from task4.errors import error_response
from task4.limiter import TokenLimiter
from task4.router import CompletionRequest, ModelRouter, ProviderFailure


logger = logging.getLogger("task4.gateway")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
logger.propagate = False


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    path = await init()
    client = httpx.AsyncClient(
        timeout=None,
        trust_env=False,
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
    )
    app.state.limiter = TokenLimiter(
        limit=int(os.getenv("TASK4_TOKEN_LIMIT", "50000")), path=path
    )
    app.state.router = ModelRouter(
        client,
        os.getenv(
            "TASK4_PRIMARY_URL", "http://127.0.0.1:8201/primary/v1/completions"
        ),
        os.getenv(
            "TASK4_SECONDARY_URL", "http://127.0.0.1:8201/secondary/v1/completions"
        ),
        float(os.getenv("TASK4_PRIMARY_TIMEOUT_SECONDS", "3.0")),
        float(os.getenv("TASK4_SECONDARY_TIMEOUT_SECONDS", "3.0")),
    )
    try:
        yield
    finally:
        await client.aclose()


app = FastAPI(title="Task 4 Rate-Limit and Fallback Gateway", lifespan=lifespan)
MAX_BODY_BYTES = 65_536
MAX_TENANT_KEY_LENGTH = 256
DEFAULT_MAX_TOKENS = 4_096


def gateway_error(
    request_id: str,
    code: str,
    message: str,
    status_code: int,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    logger.warning("event=request_rejected request_id=%s code=%s", request_id, code)
    response = error_response(
        code=code, message=message, request_id=request_id, status_code=status_code
    )
    if headers:
        response.headers.update(headers)
    return response


def rate_headers(current_usage: int, limit: int, retry_after: int | None = None) -> dict[str, str]:
    headers = {
        "x-ratelimit-limit-tokens": str(limit),
        "x-ratelimit-remaining-tokens": str(max(0, limit - current_usage)),
    }
    if retry_after is not None:
        headers["retry-after"] = str(retry_after)
    return headers


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
    if (
        tenant_key is None
        or not tenant_key.strip()
        or len(tenant_key) > MAX_TENANT_KEY_LENGTH
        or any(ord(character) < 32 or ord(character) == 127 for character in tenant_key)
    ):
        return gateway_error(
            request_id, "MISSING_TENANT_KEY", "x-tenant-key header is required", 401
        )

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_BODY_BYTES or int(content_length) < 0:
                return gateway_error(request_id, "INVALID_REQUEST", "Request body is too large", 413)
        except ValueError:
            return gateway_error(request_id, "INVALID_REQUEST", "Invalid content length", 400)
    raw_body = await request.body()
    if len(raw_body) > MAX_BODY_BYTES:
        return gateway_error(request_id, "INVALID_REQUEST", "Request body is too large", 413)
    try:
        payload = json.loads(raw_body)
    except (JSONDecodeError, UnicodeDecodeError):
        return gateway_error(request_id, "INVALID_JSON", "Request body must be valid JSON", 400)
    if not isinstance(payload, dict):
        return gateway_error(request_id, "INVALID_REQUEST", "Request body must be an object", 400)

    prompt = payload.get("prompt")
    max_tokens = payload.get("max_tokens", DEFAULT_MAX_TOKENS)
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

    # Reproducible estimate; a production adapter would use the model tokenizer.
    estimated_tokens = (len(prompt) + 3) // 4 + max_tokens
    decision = await request.app.state.limiter.try_reserve(
        tenant_key.strip(), estimated_tokens
    )
    if not decision.allowed:
        return gateway_error(
            request_id,
            "RATE_LIMITED",
            "Token limit exceeded",
            429,
            rate_headers(decision.current_usage, decision.limit, decision.retry_after_seconds),
        )

    try:
        result = await request.app.state.router.complete(CompletionRequest(prompt, max_tokens))
    except asyncio.CancelledError:
        await request.app.state.limiter.release(decision.request_id)
        logger.info("event=client_cancelled request_id=%s reservation=released", request_id)
        raise
    except ProviderFailure:
        await request.app.state.limiter.release(decision.request_id)
        logger.exception("event=providers_failed request_id=%s", request_id)
        return gateway_error(
            request_id,
            "PROVIDER_UNAVAILABLE",
            "Completion providers unavailable",
            503,
            rate_headers(decision.current_usage - estimated_tokens, decision.limit),
        )
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
        headers={
            "x-request-id": request_id,
            **rate_headers(
                decision.current_usage - estimated_tokens
                + result.prompt_tokens
                + result.completion_tokens,
                decision.limit,
            ),
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("task4.app:app", host="127.0.0.1", port=8200)
