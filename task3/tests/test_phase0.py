from __future__ import annotations

import json

import httpx
import pytest

from task3.provider.mock_provider import FIXTURES, app, split_text


def test_card_fixture_defaults_support_one_character_frames() -> None:
    assert split_text(FIXTURES["card"], 1)[-20:] == list(FIXTURES["card"][-20:])


@pytest.mark.asyncio
@pytest.mark.parametrize("fixture", list(FIXTURES))
async def test_provider_emits_openai_sse_and_terminal_sentinel(fixture: str) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://provider") as client:
        response = await client.post(
            "/v1/chat/completions", json={"fixture": fixture, "chunk_size": 3, "delay_ms": 0}
        )
    assert response.status_code == 200
    frames = [line[6:] for line in response.text.splitlines() if line.startswith("data: ")]
    assert frames[-1] == "[DONE]"
    chunks = [json.loads(frame) for frame in frames[:-1]]
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"
    content = "".join(chunk["choices"][0]["delta"].get("content", "") for chunk in chunks)
    assert content == FIXTURES[fixture]


@pytest.mark.asyncio
async def test_provider_unknown_fixture_falls_back_safely() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://provider") as client:
        response = await client.post(
            "/v1/chat/completions", json={"fixture": "unknown", "delay_ms": 0}
        )
    frames = [line[6:] for line in response.text.splitlines() if line.startswith("data: ")]
    chunks = [json.loads(frame) for frame in frames[:-1]]
    content = "".join(chunk["choices"][0]["delta"].get("content", "") for chunk in chunks)
    assert content == FIXTURES["plain"]


@pytest.mark.asyncio
async def test_single_fixture_has_exactly_one_content_delta() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://provider") as client:
        response = await client.post(
            "/v1/chat/completions", json={"fixture": "single", "chunk_size": 1, "delay_ms": 0}
        )
    frames = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: {")]
    content_frames = [frame for frame in frames if frame["choices"][0]["delta"].get("content")]
    assert len(content_frames) == 1


@pytest.mark.asyncio
async def test_card_fixture_defaults_to_one_character_content_deltas() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://provider") as client:
        response = await client.post(
            "/v1/chat/completions", json={"fixture": "card", "delay_ms": 0}
        )
    frames = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: {")]
    pieces = [frame["choices"][0]["delta"].get("content", "") for frame in frames]
    assert all(len(piece) == 1 for piece in pieces if piece)
    assert "".join(pieces) == FIXTURES["card"]


@pytest.mark.asyncio
async def test_malformed_fixture_emits_deliberately_invalid_data_frame() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://provider") as client:
        response = await client.post(
            "/v1/chat/completions", json={"fixture": "malformed", "delay_ms": 0}
        )
    assert response.text == "data: {not-json}\n\n"


@pytest.mark.asyncio
async def test_hang_fixture_can_be_shortened_for_deterministic_validation() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://provider") as client:
        response = await client.post(
            "/v1/chat/completions", json={"fixture": "hang", "hang_ms": 1}
        )
    assert response.status_code == 200
    assert response.content == b""


@pytest.mark.asyncio
async def test_disconnect_fixture_raises_after_partial_body_in_process() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://provider") as client:
        with pytest.raises(RuntimeError, match="intentional mock provider disconnect"):
            await client.post(
                "/v1/chat/completions", json={"fixture": "disconnect", "delay_ms": 0}
            )
