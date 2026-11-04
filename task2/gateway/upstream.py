import json
from typing import Any

import httpx


class UpstreamFailure(Exception):
    """A downstream failure safe to collapse at the gateway boundary."""


class UpstreamClient:
    def __init__(self, base_url: str) -> None:
        timeout = httpx.Timeout(connect=2.0, read=5.0, write=5.0, pool=2.0)
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout, trust_env=False)

    async def close(self) -> None:
        await self._client.aclose()

    async def forward(self, body: bytes, content_type: str) -> dict[str, Any]:
        try:
            response = await self._client.post(
                "/mcp",
                content=body,
                headers={"content-type": content_type},
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            raise UpstreamFailure from exc

        if not isinstance(payload, dict):
            raise UpstreamFailure
        return payload
