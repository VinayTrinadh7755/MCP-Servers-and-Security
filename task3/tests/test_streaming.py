from __future__ import annotations

import hashlib
import json

from task3.gateway.redactor import MAX_PATTERN_LEN, StreamRedactor
from task3.gateway.sse import DeltaGuardrail, encode_data


ONE_MIB = 1024 * 1024


def _delta(content: str) -> str:
    payload = {
        "id": "streaming-test",
        "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}],
    }
    return encode_data(payload).decode().strip()


def test_one_megabyte_single_token_keeps_buffer_bounded() -> None:
    # Conceptually one enormous token: no whitespace or useful boundaries.
    source = "x" * ONE_MIB
    expected_hash = hashlib.sha256(source.encode()).digest()
    actual_hash = hashlib.sha256()
    redactor = StreamRedactor()
    peak_buffer = 0
    emitted = 0
    for offset in range(0, len(source), 1024):
        output = redactor.feed(source[offset : offset + 1024])
        actual_hash.update(output.encode())
        emitted += len(output)
        peak_buffer = max(peak_buffer, redactor.buffered_characters)
    tail = redactor.flush()
    actual_hash.update(tail.encode())
    emitted += len(tail)

    assert emitted == ONE_MIB
    assert actual_hash.digest() == expected_hash
    assert peak_buffer <= MAX_PATTERN_LEN * 2


def test_ten_thousand_one_character_frames_remain_bounded_and_exact() -> None:
    guardrail = DeltaGuardrail()
    peak_buffer = 0
    assembled_length = 0
    for _ in range(10_000):
        result = guardrail.process(_delta("x"))
        peak_buffer = max(peak_buffer, guardrail.redactor.buffered_characters)
        for frame in result.frames:
            payload = json.loads(frame.decode().splitlines()[0][6:])
            assembled_length += len(payload["choices"][0]["delta"]["content"])
    final = guardrail.process("data: [DONE]")
    for frame in final.frames[:-1]:
        payload = json.loads(frame.decode().splitlines()[0][6:])
        assembled_length += len(payload["choices"][0]["delta"].get("content", ""))

    assert assembled_length == 10_000
    assert peak_buffer <= MAX_PATTERN_LEN * 2
    assert final.frames[-1] == b"data: [DONE]\n\n"


def test_repeated_pattern_like_input_does_not_accumulate() -> None:
    redactor = StreamRedactor()
    near_matches = ("4111-1111-1111-x " * 20_000)
    emitted = 0
    peak_buffer = 0
    for offset in range(0, len(near_matches), 17):
        emitted += len(redactor.feed(near_matches[offset : offset + 17]))
        peak_buffer = max(peak_buffer, redactor.buffered_characters)
    emitted += len(redactor.flush())
    assert emitted == len(near_matches)
    assert peak_buffer <= MAX_PATTERN_LEN * 2
