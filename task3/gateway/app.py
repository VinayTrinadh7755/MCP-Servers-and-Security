"""Streaming gateway that redacts PII inside OpenAI content deltas."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

from task3.gateway.sse import DeltaGuardrail, MalformedSSE, SSEDecoder, encode_data, error_event


app = FastAPI(title="Task 3 Streaming Guardrail Gateway")
logger = logging.getLogger("task3.gateway")


async def guarded_relay(
    body: bytes,
    target: str,
    content_type: str,
    client_factory: type[httpx.AsyncClient] = httpx.AsyncClient,
    provider_api_key: str | None = None,
) -> AsyncIterator[bytes]:
    """Stream one upstream response through one request-scoped guardrail."""

    decoder = SSEDecoder()
    guardrail = DeltaGuardrail()
    upstream_headers = {"content-type": content_type}
    if provider_api_key:
        upstream_headers["authorization"] = f"Bearer {provider_api_key}"
    async with client_factory(timeout=httpx.Timeout(30.0), trust_env=False) as client:
        try:
            async with client.stream(
                "POST", target, content=body, headers=upstream_headers
            ) as response:
                response.raise_for_status()
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


@app.post("/v1/chat/completions")
async def chat_completions(request: Request) -> StreamingResponse:
    body = await request.body()
    provider_url = os.getenv(
        "TASK3_PROVIDER_URL", "http://127.0.0.1:8101/v1/chat/completions"
    )
    query = request.url.query
    target = f"{provider_url}?{query}" if query else provider_url

    async def relay() -> AsyncIterator[bytes]:
        async for frame in guarded_relay(
            body,
            target,
            request.headers.get("content-type", "application/json"),
            provider_api_key=os.getenv("TASK3_PROVIDER_API_KEY"),
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
