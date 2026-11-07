"""Timeout-bounded primary/secondary model router."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx


@dataclass(frozen=True, slots=True)
class CompletionRequest:
    prompt: str
    max_tokens: int


@dataclass(frozen=True, slots=True)
class CompletionResult:
    provider: str
    text: str
    prompt_tokens: int
    completion_tokens: int
    failed_over: bool


class ProviderFailure(Exception):
    """Sanitized signal that neither provider produced a valid completion."""


class InvalidProviderResponse(Exception):
    pass


class ModelRouter:
    def __init__(
        self,
        client: httpx.AsyncClient,
        primary_url: str,
        secondary_url: str,
        primary_timeout: float = 3.0,
        secondary_timeout: float = 3.0,
    ) -> None:
        self.client = client
        self.primary_url = primary_url
        self.secondary_url = secondary_url
        self.primary_timeout = primary_timeout
        self.secondary_timeout = secondary_timeout

    async def _call(
        self, provider: str, url: str, request: CompletionRequest, timeout: float
    ) -> CompletionResult:
        async with asyncio.timeout(timeout):
            response = await self.client.post(
                url,
                json={"prompt": request.prompt, "max_tokens": request.max_tokens},
            )
        if response.status_code == 429:
            raise httpx.HTTPStatusError(
                "provider rate limited", request=response.request, response=response
            )
        response.raise_for_status()
        try:
            payload = response.json()
            usage = payload["usage"]
            text = payload["text"]
            prompt_tokens = usage["prompt_tokens"]
            completion_tokens = usage["completion_tokens"]
            if (
                not isinstance(text, str)
                or isinstance(prompt_tokens, bool)
                or not isinstance(prompt_tokens, int)
                or prompt_tokens < 0
                or isinstance(completion_tokens, bool)
                or not isinstance(completion_tokens, int)
                or completion_tokens < 0
            ):
                raise InvalidProviderResponse
        except (KeyError, TypeError, ValueError, InvalidProviderResponse) as exc:
            raise InvalidProviderResponse from exc
        return CompletionResult(
            provider=provider,
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            failed_over=provider == "secondary",
        )

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        try:
            return await self._call(
                "primary", self.primary_url, request, self.primary_timeout
            )
        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError:
            pass
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 429:
                raise ProviderFailure from exc
        except (httpx.HTTPError, InvalidProviderResponse) as exc:
            raise ProviderFailure from exc

        try:
            return await self._call(
                "secondary", self.secondary_url, request, self.secondary_timeout
            )
        except asyncio.CancelledError:
            raise
        except (asyncio.TimeoutError, httpx.HTTPError, InvalidProviderResponse) as exc:
            raise ProviderFailure from exc
