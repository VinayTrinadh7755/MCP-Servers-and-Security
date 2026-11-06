from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from task3.gateway.app import guarded_relay, validate_stream_request
from task3.gateway.redactor import REDACTION
from task3.gateway.sse import DeltaGuardrail, MalformedSSE, SSEDecoder, encode_data


def delta(content: str, *, finish_reason: str | None = None) -> dict[str, Any]:
    return {
        "id": "test",
        "object": "chat.completion.chunk",
        "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": finish_reason}],
    }


def finish() -> dict[str, Any]:
    return {
        "id": "test",
        "object": "chat.completion.chunk",
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }


def event_text(payload: dict[str, Any] | str) -> str:
    return encode_data(payload).decode().strip()


def run_guardrail(chunks: list[str], *, include_done: bool = True) -> tuple[str, list[bytes], DeltaGuardrail]:
    guardrail = DeltaGuardrail()
    frames: list[bytes] = []
    for chunk in chunks:
        frames.extend(guardrail.process(event_text(delta(chunk))).frames)
    frames.extend(guardrail.process(event_text(finish())).frames)
    if include_done:
        frames.extend(guardrail.process("data: [DONE]").frames)
    else:
        frames.extend(guardrail.finish_without_sentinel())

    assembled: list[str] = []
    for frame in frames:
        data = frame.decode().splitlines()[0][6:]
        if data == "[DONE]":
            continue
        payload = json.loads(data)
        choices = payload.get("choices", [])
        if choices:
            assembled.append(choices[0]["delta"].get("content", ""))
    return "".join(assembled), frames, guardrail


def test_decoder_handles_every_utf8_byte_boundary_and_crlf() -> None:
    wire = 'data: {"message":"café 🔒"}\r\n\r\n'.encode()
    decoder = SSEDecoder()
    events: list[str] = []
    for byte in wire:
        events.extend(decoder.feed(bytes([byte])))
    events.extend(decoder.finish())
    assert events == ['data: {"message":"café 🔒"}']


@pytest.mark.parametrize(
    ("value", "expected", "kind"),
    (
        ("ada@example.com", REDACTION, "email"),
        ("123-45-6789", REDACTION, "ssn"),
        ("4111-1111-1111-1111", REDACTION, "card"),
    ),
)
def test_pii_split_one_character_per_sse_frame(value: str, expected: str, kind: str) -> None:
    assembled, frames, guardrail = run_guardrail(list(value))
    assert assembled == expected
    assert guardrail.redaction_counts[kind] == 1
    assert frames[-1] == b"data: [DONE]\n\n"


def test_clean_content_is_byte_identical_when_assembled() -> None:
    clean = "The clean response remains exactly the same, including punctuation."
    assembled, _, guardrail = run_guardrail(list(clean))
    assert assembled == clean
    assert guardrail.redaction_counts == {"ssn": 0, "card": 0, "email": 0}


def test_pii_at_end_is_flushed_before_finish_and_sentinel() -> None:
    assembled, frames, _ = run_guardrail(["final: ", "ada@", "example.com"])
    assert assembled == f"final: {REDACTION}"
    decoded = [frame.decode() for frame in frames]
    flush_index = next(index for index, frame in enumerate(decoded) if REDACTION in frame)
    finish_index = next(index for index, frame in enumerate(decoded) if '"finish_reason":"stop"' in frame)
    assert flush_index < finish_index < len(frames) - 1
    assert decoded[-1] == "data: [DONE]\n\n"


def test_missing_upstream_sentinel_is_added_once() -> None:
    assembled, frames, _ = run_guardrail(["clean"], include_done=False)
    assert assembled == "clean"
    assert frames.count(b"data: [DONE]\n\n") == 1


def test_usage_frame_is_preserved_and_terminal_is_not_duplicated() -> None:
    guardrail = DeltaGuardrail()
    usage = {"usage": {"completion_tokens": 3}, "choices": []}
    assert guardrail.process(event_text(usage)).frames == [encode_data(usage)]
    first = guardrail.process("data: [DONE]")
    second = guardrail.process("data: [DONE]")
    assert first.frames[-1] == b"data: [DONE]\n\n"
    assert second.frames == []


def test_sse_comment_and_event_only_fields_are_preserved() -> None:
    guardrail = DeltaGuardrail()
    assert guardrail.process(": ping").frames == [b": ping\n\n"]
    assert guardrail.process("event: heartbeat").frames == [b"event: heartbeat\n\n"]


def test_content_after_done_is_discarded() -> None:
    guardrail = DeltaGuardrail()
    guardrail.process("data: [DONE]")
    assert guardrail.process(event_text(delta("must not appear"))).frames == []


def test_empty_content_metadata_frame_is_preserved() -> None:
    guardrail = DeltaGuardrail()
    payload = delta("")
    payload["choices"][0]["delta"]["role"] = "assistant"
    assert guardrail.process(event_text(payload)).frames == [encode_data(payload)]


@pytest.mark.parametrize(
    "event",
    (
        "data: {not-json}",
        "data: []",
        'data: {"choices":{}}',
        'data: {"choices":[{"delta":{"content":"safe"}},{"delta":{"content":"ada@example.com"}}]}',
        'data: {"choices":[{"delta":7}]}',
        'data: {"choices":[{"delta":{"content":7}}]}',
    ),
)
def test_malformed_frames_fail_closed(event: str) -> None:
    with pytest.raises(MalformedSSE):
        DeltaGuardrail().process(event)


def test_request_scoped_instances_cannot_mix_tenants() -> None:
    first = DeltaGuardrail()
    second = DeltaGuardrail()
    first.process(event_text(delta("ada@")))
    second.process(event_text(delta("safe response")))
    first_frames = first.process(event_text(delta("example.com"))).frames
    first_frames.extend(first.process("data: [DONE]").frames)
    second_frames = second.process("data: [DONE]").frames
    assert REDACTION in b"".join(first_frames).decode()
    assert "safe response" in b"".join(second_frames).decode()
    assert "ada" not in b"".join(second_frames).decode()


class FakeResponse:
    def __init__(self) -> None:
        self.closed = False
        self.headers = {"content-type": "text/event-stream; charset=utf-8"}

    async def __aenter__(self) -> "FakeResponse":
        return self

    async def __aexit__(self, *args: object) -> None:
        self.closed = True

    def raise_for_status(self) -> None:
        return None

    async def aiter_raw(self):
        yield encode_data(delta("x" * 300))
        yield encode_data(delta("later upstream data"))


class FakeClient:
    response = FakeResponse()
    last_headers: dict[str, str] = {}

    def __init__(self, **kwargs: object) -> None:
        pass

    async def __aenter__(self) -> "FakeClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    def stream(self, *args: object, **kwargs: object) -> FakeResponse:
        type(self).last_headers = kwargs.get("headers", {})  # type: ignore[assignment]
        return self.response


@pytest.mark.asyncio
async def test_closing_downstream_generator_closes_upstream_context() -> None:
    FakeClient.response = FakeResponse()
    stream = guarded_relay(b"{}", "http://provider", "application/json", FakeClient)  # type: ignore[arg-type]
    first = await anext(stream)
    assert first.startswith(b"data: ")
    await stream.aclose()
    assert FakeClient.response.closed


@pytest.mark.asyncio
async def test_downstream_cancellation_propagates_and_closes_upstream() -> None:
    FakeClient.response = FakeResponse()
    stream = guarded_relay(b"{}", "http://provider", "application/json", FakeClient)  # type: ignore[arg-type]
    await anext(stream)
    with pytest.raises(asyncio.CancelledError):
        await stream.athrow(asyncio.CancelledError())
    assert FakeClient.response.closed


@pytest.mark.asyncio
async def test_provider_key_is_server_side_and_sent_as_bearer() -> None:
    FakeClient.response = FakeResponse()
    stream = guarded_relay(
        b"{}", "http://provider", "application/json", FakeClient, provider_api_key="secret-key"  # type: ignore[arg-type]
    )
    await anext(stream)
    await stream.aclose()
    assert FakeClient.last_headers == {
        "content-type": "application/json",
        "authorization": "Bearer secret-key",
    }


class MalformedClient(FakeClient):
    response = FakeResponse()

    def stream(self, *args: object, **kwargs: object) -> FakeResponse:
        response = FakeResponse()

        async def malformed_chunks():
            yield b"data: {not-json}\n\n"

        response.aiter_raw = malformed_chunks  # type: ignore[method-assign]
        return response


@pytest.mark.asyncio
async def test_gateway_converts_malformed_upstream_to_error_and_done() -> None:
    frames = [
        frame
        async for frame in guarded_relay(
            b"{}", "http://provider", "application/json", MalformedClient  # type: ignore[arg-type]
        )
    ]
    assert json.loads(frames[0].decode().splitlines()[0][6:])["error"]["type"] == "gateway_stream_error"
    assert frames[-1] == b"data: [DONE]\n\n"


@pytest.mark.parametrize(
    ("body", "message"),
    (
        (b"not-json", "valid JSON"),
        (b"[]", "JSON object"),
        (b'{"stream":false}', "requires stream=true"),
        (b'{"stream":"true"}', "stream must be a boolean"),
        (b'{"stream":true,"n":2}', "exactly one choice"),
    ),
)
def test_invalid_stream_controls_are_rejected_before_forwarding(body: bytes, message: str) -> None:
    validated, error = validate_stream_request(body)
    assert validated is None
    assert error is not None and message in error


def test_unknown_request_fields_are_preserved_and_stream_is_forced_true() -> None:
    validated, error = validate_stream_request(b'{"model":"demo","extra":"kept"}')
    assert error is None
    assert json.loads(validated) == {"model": "demo", "extra": "kept", "stream": True}


class WrongContentTypeClient(FakeClient):
    def stream(self, *args: object, **kwargs: object) -> FakeResponse:
        response = FakeResponse()
        response.headers = {"content-type": "application/json"}
        return response


@pytest.mark.asyncio
async def test_non_sse_provider_content_type_fails_closed() -> None:
    frames = [
        frame
        async for frame in guarded_relay(
            b"{}", "http://provider", "application/json", WrongContentTypeClient  # type: ignore[arg-type]
        )
    ]
    assert json.loads(frames[0].decode().splitlines()[0][6:])["error"]["type"] == "gateway_stream_error"
    assert frames[-1] == b"data: [DONE]\n\n"
