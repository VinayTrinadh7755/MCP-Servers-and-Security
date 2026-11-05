import json
from typing import Any

import httpx


class UpstreamFailure(Exception):
    """A downstream failure safe to collapse at the gateway boundary."""


class UpstreamClient:
    def __init__(
        self,
        base_url: str,
        *,
        read_timeout: float = 5.0,
        max_response_bytes: int = 1_048_576,
    ) -> None:
        timeout = httpx.Timeout(connect=2.0, read=read_timeout, write=5.0, pool=2.0)
        self._max_response_bytes = max_response_bytes
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout, trust_env=False)

    async def close(self) -> None:
        await self._client.aclose()

    async def forward(self, body: bytes, content_type: str) -> dict[str, Any]:
        try:
            async with self._client.stream(
                "POST", "/mcp", content=body, headers={"content-type": content_type}
            ) as response:
                response.raise_for_status()
                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(raw) + len(chunk) > self._max_response_bytes:
                        raise UpstreamFailure
                    raw.extend(chunk)
            payload = json.loads(raw)
        except UpstreamFailure:
            raise
        except (httpx.HTTPError, json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            raise UpstreamFailure from exc

        if not isinstance(payload, dict):
            raise UpstreamFailure
        return payload
