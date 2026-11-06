"""Deterministic OpenAI-compatible streaming provider used by Task 3 tests."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import StreamingResponse


FIXTURES = {
    "plain": "Streaming proves that each delta reaches the client progressively.",
    "email": "Contact Ada at ada.lovelace@example.com for details.",
    "ssn": "The test SSN is 123-45-6789 and must eventually be redacted.",
    "card": "The test card is 4111-1111-1111-1111 and must eventually be redacted.",
    "card-split-one-char": "The test card is 4111-1111-1111-1111 and must eventually be redacted.",
    "mixed": "Email ada@example.com, SSN 123-45-6789, card 4111111111111111.",
    "pii-end": "The final value is ada@example.com",
    "single": "one frame",
    "empty": "",
}


def _sse(payload: dict[str, Any] | str) -> bytes:
    body = payload if isinstance(payload, str) else json.dumps(payload, separators=(",", ":"))
    return f"data: {body}\n\n".encode("utf-8")


def _delta(text: str) -> dict[str, Any]:
    return {
        "id": "chatcmpl-task3-mock",
        "object": "chat.completion.chunk",
        "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
    }


def _finish() -> dict[str, Any]:
    return {
        "id": "chatcmpl-task3-mock",
        "object": "chat.completion.chunk",
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }


def split_text(text: str, chunk_size: int) -> list[str]:
    return [text[index : index + chunk_size] for index in range(0, len(text), chunk_size)]


app = FastAPI(title="Task 3 Mock LLM Provider")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    fixture: str | None = Query(default=None),
    chunk_size: int | None = Query(default=None, ge=1, le=4096),
    delay_ms: int | None = Query(default=None, ge=0, le=10_000),
) -> StreamingResponse:
    body = await request.json()
    selected = fixture or body.get("fixture", "plain")
    custom_text = body.get("text")
    if custom_text is not None and not isinstance(custom_text, str):
        custom_text = None
    if (
        selected not in FIXTURES
        and selected not in {"disconnect", "malformed", "hang"}
        and custom_text is None
    ):
        selected = "plain"

    configured_size = chunk_size or int(body.get("chunk_size", os.getenv("TASK3_CHUNK_SIZE", "8")))
    if configured_size < 1 or configured_size > 4096:
        configured_size = 8
    # The card fixture deliberately defaults to one character per SSE frame.
    if selected in {"card", "card-split-one-char"} and chunk_size is None and "chunk_size" not in body:
        configured_size = 1
    if selected == "single":
        configured_size = max(1, len(FIXTURES["single"]))
    configured_delay = delay_ms if delay_ms is not None else int(
        body.get("delay_ms", os.getenv("TASK3_PROVIDER_DELAY_MS", "20"))
    )

    async def events() -> AsyncIterator[bytes]:
        if selected == "hang":
            hang_ms = int(body.get("hang_ms", 60_000))
            await asyncio.sleep(max(0, min(hang_ms, 60_000)) / 1000)
            return
        if selected == "malformed":
            yield b"data: {not-json}\n\n"
            return
        if selected == "disconnect":
            yield _sse(_delta("partial response"))
            await asyncio.sleep(configured_delay / 1000)
            # Simulate an upstream generator failing after headers and one frame.
            raise RuntimeError("intentional mock provider disconnect")

        content = custom_text if custom_text is not None else FIXTURES[selected]
        for piece in split_text(content, configured_size):
            yield _sse(_delta(piece))
            await asyncio.sleep(configured_delay / 1000)
        yield _sse(_finish())
        yield _sse("[DONE]")

    return StreamingResponse(events(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("task3.provider.mock_provider:app", host="127.0.0.1", port=8101)
