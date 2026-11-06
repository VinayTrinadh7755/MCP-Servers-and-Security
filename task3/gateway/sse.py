"""Incremental SSE decoding and OpenAI-delta redaction."""

from __future__ import annotations

import codecs
import json
from dataclasses import dataclass
from typing import Any

from task3.gateway.redactor import StreamRedactor


DONE = "[DONE]"


class MalformedSSE(ValueError):
    """Raised when an upstream data frame cannot be handled safely."""


class SSEDecoder:
    """Decode arbitrarily chunked UTF-8 bytes into complete SSE event blocks."""

    def __init__(self) -> None:
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="strict")
        self._buffer = ""

    def feed(self, chunk: bytes) -> list[str]:
        self._buffer += self._decoder.decode(chunk)
        return self._drain()

    def finish(self) -> list[str]:
        self._buffer += self._decoder.decode(b"", final=True)
        events = self._drain()
        if self._buffer.strip():
            events.append(self._buffer.rstrip("\r\n"))
        self._buffer = ""
        return events

    def _drain(self) -> list[str]:
        self._buffer = self._buffer.replace("\r\n", "\n").replace("\r", "\n")
        events: list[str] = []
        while "\n\n" in self._buffer:
            event, self._buffer = self._buffer.split("\n\n", 1)
            if event:
                events.append(event)
        return events


def encode_data(data: str | dict[str, Any]) -> bytes:
    payload = data if isinstance(data, str) else json.dumps(data, separators=(",", ":"))
    return f"data: {payload}\n\n".encode("utf-8")


def error_event(message: str = "upstream stream was malformed") -> bytes:
    return encode_data({"error": {"message": message, "type": "gateway_stream_error"}})


def _data_from_event(event: str) -> str | None:
    values: list[str] = []
    for line in event.splitlines():
        if line.startswith(":"):
            continue
        field, separator, value = line.partition(":")
        if field == "data":
            values.append(value[1:] if separator and value.startswith(" ") else value)
    return "\n".join(values) if values else None


@dataclass
class GuardrailResult:
    frames: list[bytes]
    terminal: bool = False


class DeltaGuardrail:
    """Apply one request-scoped redactor to OpenAI content-delta SSE events."""

    def __init__(self) -> None:
        self.redactor = StreamRedactor()
        self._content_template: dict[str, Any] | None = None
        self._finish_frames: list[bytes] = []
        self.terminal = False

    @property
    def redaction_counts(self) -> dict[str, int]:
        return dict(self.redactor.redaction_counts)

    def process(self, event: str) -> GuardrailResult:
        if self.terminal:
            return GuardrailResult([])
        data = _data_from_event(event)
        if data is None:
            return GuardrailResult([(event + "\n\n").encode("utf-8")])
        if data.strip() == DONE:
            self.terminal = True
            return GuardrailResult(self._final_frames(), terminal=True)

        try:
            payload = json.loads(data)
        except json.JSONDecodeError as exc:
            raise MalformedSSE("upstream data was not valid JSON") from exc
        if not isinstance(payload, dict):
            raise MalformedSSE("upstream data payload was not an object")
        choices = payload.get("choices")
        if choices is None or choices == []:
            return GuardrailResult([encode_data(payload)])
        if (
            not isinstance(choices, list)
            or len(choices) != 1
            or not isinstance(choices[0], dict)
        ):
            raise MalformedSSE("upstream choices had an invalid shape")
        choice = choices[0]
        delta = choice.get("delta")
        if not isinstance(delta, dict):
            raise MalformedSSE("upstream delta had an invalid shape")
        content = delta.get("content")
        if content is not None and not isinstance(content, str):
            raise MalformedSSE("upstream delta content was not text")

        if content is not None:
            # Empty content is safe and may accompany useful provider metadata.
            if content == "":
                return GuardrailResult([encode_data(payload)])
            self._content_template = payload
            safe = self.redactor.feed(content)
            if not safe:
                return GuardrailResult([])
            delta["content"] = safe
            return GuardrailResult([encode_data(payload)])
        if choice.get("finish_reason") is not None:
            self._finish_frames.append(encode_data(payload))
            return GuardrailResult([])
        return GuardrailResult([encode_data(payload)])

    def finish_without_sentinel(self) -> list[bytes]:
        if self.terminal:
            return []
        self.terminal = True
        return self._final_frames()

    def _final_frames(self) -> list[bytes]:
        frames: list[bytes] = []
        tail = self.redactor.flush()
        if tail:
            if self._content_template is None:
                raise MalformedSSE("text tail had no content-frame template")
            payload = json.loads(json.dumps(self._content_template))
            payload["choices"][0]["delta"]["content"] = tail
            payload["choices"][0]["finish_reason"] = None
            frames.append(encode_data(payload))
        frames.extend(self._finish_frames)
        frames.append(encode_data(DONE))
        return frames
