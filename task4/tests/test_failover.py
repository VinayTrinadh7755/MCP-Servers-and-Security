from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from task4.router import CompletionRequest, ModelRouter, ProviderFailure


def provider_response(request: httpx.Request, provider: str) -> httpx.Response:
    return httpx.Response(
        200,
        request=request,
        json={
            "provider": provider,
            "text": f"from {provider}",
            "usage": {"prompt_tokens": 2, "completion_tokens": 3},
        },
    )


@pytest.mark.asyncio
async def test_primary_success_does_not_call_secondary() -> None:
    calls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return provider_response(request, "primary")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        router = ModelRouter(client, "http://mock/primary", "http://mock/secondary", 0.1, 0.1)
        result = await router.complete(CompletionRequest("hello", 10))
    assert result.provider == "primary"
    assert not result.failed_over
    assert calls == ["/primary"]


@pytest.mark.parametrize("status", [429])
@pytest.mark.asyncio
async def test_primary_429_falls_back(status) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/primary":
            return httpx.Response(status, request=request, json={"internal": "do not leak"})
        return provider_response(request, "secondary")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await ModelRouter(
            client, "http://mock/primary", "http://mock/secondary", 0.1, 0.1
        ).complete(CompletionRequest("hello", 10))
    assert result.provider == "secondary"
    assert result.failed_over


@pytest.mark.asyncio
async def test_primary_timeout_is_cancelled_then_secondary_serves() -> None:
    cancelled = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/primary":
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise
        return provider_response(request, "secondary")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await ModelRouter(
            client, "http://mock/primary", "http://mock/secondary", 0.02, 0.1
        ).complete(CompletionRequest("hello", 10))
    assert result.provider == "secondary"
    assert cancelled.is_set()


@pytest.mark.asyncio
async def test_secondary_timeout_and_primary_500_are_sanitized_failure() -> None:
    async def both_hang(request: httpx.Request) -> httpx.Response:
        await asyncio.Event().wait()

    async with httpx.AsyncClient(transport=httpx.MockTransport(both_hang)) as client:
        with pytest.raises(ProviderFailure):
            await ModelRouter(
                client, "http://mock/primary", "http://mock/secondary", 0.01, 0.01
            ).complete(CompletionRequest("hello", 10))

    async def primary_500(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, request=request, text="secret upstream traceback")

    async with httpx.AsyncClient(transport=httpx.MockTransport(primary_500)) as client:
        with pytest.raises(ProviderFailure):
            await ModelRouter(
                client, "http://mock/primary", "http://mock/secondary", 0.1, 0.1
            ).complete(CompletionRequest("hello", 10))


@pytest.mark.asyncio
async def test_invalid_provider_payload_fails_closed() -> None:
    async def invalid(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request, content=json.dumps({"text": 7}))

    async with httpx.AsyncClient(transport=httpx.MockTransport(invalid)) as client:
        with pytest.raises(ProviderFailure):
            await ModelRouter(
                client, "http://mock/primary", "http://mock/secondary", 0.1, 0.1
            ).complete(CompletionRequest("hello", 10))
