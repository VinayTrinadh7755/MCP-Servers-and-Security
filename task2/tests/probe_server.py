import asyncio
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


app = FastAPI()
calls: list[dict[str, Any]] = []
hangs = {"started": 0, "active": 0, "abandoned": 0, "completed": 0}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/state")
async def state() -> dict[str, Any]:
    return {"calls": calls, "hangs": hangs}


@app.post("/mcp")
async def mcp(request: Request) -> JSONResponse:
    payload = await request.json()
    params = payload.get("params")
    name = params.get("name") if isinstance(params, dict) else None
    calls.append(
        {
            "id": payload.get("id"),
            "name": name,
            "headers": list(request.headers.items()),
        }
    )

    if name == "admin_hang":
        hangs["started"] += 1
        hangs["active"] += 1
        try:
            for _ in range(600):
                if await request.is_disconnected():
                    hangs["abandoned"] += 1
                    break
                await asyncio.sleep(0.05)
            else:
                hangs["completed"] += 1
        finally:
            hangs["active"] -= 1

    if name == "admin_large":
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": payload.get("id"),
                "result": {"blob": "x" * 2_000_000},
            }
        )

    return JSONResponse(
        {"jsonrpc": "2.0", "id": payload.get("id"), "result": {"executed": name}}
    )
