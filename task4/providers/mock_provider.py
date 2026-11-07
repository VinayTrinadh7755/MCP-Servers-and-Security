"""Credential-free primary and secondary provider fixtures."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


ProviderName = Literal["primary", "secondary"]
SUPPORTED_MODES = {"normal", "429", "hang", "slow", "500"}
app = FastAPI(title="Task 4 Mock Providers")
logger = logging.getLogger("task4.mock_provider")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
logger.propagate = False
disconnect_counts: dict[str, int] = {"primary": 0, "secondary": 0}


def selected_mode(provider: ProviderName, request: Request) -> str:
    mode = request.query_params.get("mode") or os.getenv(
        f"TASK4_{provider.upper()}_MODE", "normal"
    )
    return mode if mode in SUPPORTED_MODES else "normal"


async def response_for(provider: ProviderName, request: Request) -> JSONResponse:
    mode = selected_mode(provider, request)
    if mode == "429":
        return JSONResponse({"detail": "mock provider rate limit"}, status_code=429)
    if mode == "500":
        return JSONResponse(
            {"detail": "mock internal failure at /srv/provider/private.py"},
            status_code=500,
        )
    if mode == "hang":
        while True:
            if await request.is_disconnected():
                disconnect_counts[provider] += 1
                logger.info("provider=%s event=client_disconnected", provider)
                return JSONResponse({"detail": "client disconnected"}, status_code=499)
            await asyncio.sleep(0.02)
    if mode == "slow":
        await asyncio.sleep(float(os.getenv("TASK4_MOCK_SLOW_SECONDS", "0.25")))

    try:
        payload = await request.json()
    except ValueError:
        payload = {}
    prompt = payload.get("prompt", "") if isinstance(payload, dict) else ""
    return JSONResponse(
        {
            "provider": provider,
            "text": f"mock completion: {prompt}",
            "usage": {"prompt_tokens": len(prompt) // 4 + 1, "completion_tokens": 4},
        }
    )


@app.post("/primary/v1/completions")
async def primary(request: Request) -> JSONResponse:
    return await response_for("primary", request)


@app.post("/secondary/v1/completions")
async def secondary(request: Request) -> JSONResponse:
    return await response_for("secondary", request)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/stats")
async def stats() -> dict[str, dict[str, int]]:
    return {"disconnects": dict(disconnect_counts)}


@app.post("/stats/reset")
async def reset_stats() -> dict[str, str]:
    disconnect_counts.update(primary=0, secondary=0)
    return {"status": "reset"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("task4.providers.mock_provider:app", host="127.0.0.1", port=8201)
