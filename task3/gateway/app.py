"""Streaming gateway that redacts PII inside OpenAI content deltas."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from task3.gateway.sse import DeltaGuardrail, MalformedSSE, SSEDecoder, encode_data, error_event


logger = logging.getLogger("task3.gateway")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
logger.propagate = False


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    read_timeout = float(os.getenv("TASK3_UPSTREAM_READ_TIMEOUT", "30.0"))
    app.state.upstream_client = httpx.AsyncClient(
        timeout=httpx.Timeout(connect=5.0, read=read_timeout, write=5.0, pool=5.0),
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        trust_env=False,
    )
    try:
        yield
    finally:
        await app.state.upstream_client.aclose()


app = FastAPI(title="Task 3 Streaming Guardrail Gateway", lifespan=lifespan)


async def guarded_relay(
    body: bytes,
    target: str,
    content_type: str,
    client_factory: type[httpx.AsyncClient] = httpx.AsyncClient,
    provider_api_key: str | None = None,
    read_timeout: float = 30.0,
    client: httpx.AsyncClient | None = None,
) -> AsyncIterator[bytes]:
    """Stream one upstream response through one request-scoped guardrail."""

    decoder = SSEDecoder()
    guardrail = DeltaGuardrail()
    upstream_headers = {"content-type": content_type}
    if provider_api_key:
        upstream_headers["authorization"] = f"Bearer {provider_api_key}"
    @asynccontextmanager
    async def client_scope() -> AsyncIterator[httpx.AsyncClient]:
        if client is not None:
            yield client
            return
        timeout = httpx.Timeout(connect=5.0, read=read_timeout, write=5.0, pool=5.0)
        async with client_factory(timeout=timeout, trust_env=False) as owned_client:
            yield owned_client

    async with client_scope() as upstream_client:
        try:
            async with upstream_client.stream(
                "POST", target, content=body, headers=upstream_headers
            ) as response:
                response.raise_for_status()
                media_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                if media_type != "text/event-stream":
                    raise MalformedSSE("upstream response was not text/event-stream")
                async for chunk in response.aiter_raw():
                    for event in decoder.feed(chunk):
                        result = guardrail.process(event)
                        for frame in result.frames:
                            yield frame
                        if result.terminal:
                            break
                    if guardrail.terminal:
                        break
                if not guardrail.terminal:
                    for event in decoder.finish():
                        result = guardrail.process(event)
                        for frame in result.frames:
                            yield frame
                    for frame in guardrail.finish_without_sentinel():
                        yield frame
        except asyncio.CancelledError:
            logger.info("client disconnected; cancelling upstream stream")
            raise
        except (MalformedSSE, httpx.HTTPError, UnicodeError) as exc:
            logger.warning("stream failed closed: %s", type(exc).__name__)
            yield error_event()
            yield encode_data("[DONE]")
        finally:
            logger.info("stream redactions=%s", guardrail.redaction_counts)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def validate_stream_request(body: bytes) -> tuple[bytes | None, str | None]:
    """Validate streaming controls before any provider request is opened."""

    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, "request body must be valid JSON"
    if not isinstance(payload, dict):
        return None, "request body must be a JSON object"
    if payload.get("stream") is False:
        return None, "this endpoint requires stream=true"
    if "stream" in payload and payload["stream"] is not True:
        return None, "stream must be a boolean"
    if payload.get("n", 1) != 1:
        return None, "this endpoint supports exactly one choice"
    payload["stream"] = True
    return json.dumps(payload, separators=(",", ":")).encode(), None


@app.post("/v1/chat/completions")
async def chat_completions(request: Request) -> StreamingResponse:
    body, validation_error = validate_stream_request(await request.body())
    if validation_error:
        return JSONResponse({"error": {"message": validation_error}}, status_code=400)
    assert body is not None
    provider_url = os.getenv(
        "TASK3_PROVIDER_URL", "http://127.0.0.1:8101/v1/chat/completions"
    )
    # The destination is configuration-only. Client body, query string, and
    # headers cannot select or modify the provider URL.
    target = provider_url

    async def relay() -> AsyncIterator[bytes]:
        async for frame in guarded_relay(
            body,
            target,
            request.headers.get("content-type", "application/json"),
            provider_api_key=os.getenv("TASK3_PROVIDER_API_KEY"),
            read_timeout=float(os.getenv("TASK3_UPSTREAM_READ_TIMEOUT", "30.0")),
            client=request.app.state.upstream_client,
        ):
            yield frame

    return StreamingResponse(
        relay(),
        media_type="text/event-stream",
        headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("task3.gateway.app:app", host="127.0.0.1", port=8100)
