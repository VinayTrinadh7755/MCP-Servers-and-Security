# Task 3 / Phase 2 — Live Streaming Guardrail

## Objective

Apply the validated offline redactor to parsed OpenAI-compatible SSE content
deltas while preserving streaming semantics, request isolation, cancellation,
and terminal framing.

## Implementation

### Incremental SSE transport

`task3/gateway/sse.py` adds `SSEDecoder`, which:

- Accepts arbitrarily divided byte chunks.
- Uses an incremental UTF-8 decoder, so a multibyte character split between
  network reads is reconstructed safely.
- Accepts LF, CRLF, and CR line endings.
- Emits only complete SSE event blocks and retains only the incomplete event.

### Delta-only redaction

`DeltaGuardrail` parses each `data:` payload as JSON and validates the expected
OpenAI shape. Only `choices[0].delta.content` is passed to `StreamRedactor`.
JSON field names, IDs, metadata, and SSE framing never enter the regex engine.

Each request creates its own decoder and guardrail, and therefore its own
redactor and carry buffer. No mutable redaction state is shared between users.

Responses with more than one choice fail closed. Supporting multiple choices
would require one independent redactor per choice; forwarding unchecked
secondary choices would create a PII bypass.

### Re-framing and completion order

Content frames are emitted only when `feed()` returns safe text. Because the
final content may remain in the bounded carry:

1. Finish frames are temporarily held.
2. The tail is redacted and emitted as a content frame.
3. The provider finish frame is emitted.
4. Exactly one `data: [DONE]` sentinel is emitted last.

If a valid upstream stream reaches EOF without its sentinel, the gateway adds
one. Duplicate sentinels are ignored after the first terminal event.

### Failure and cancellation behavior

- Invalid JSON, invalid delta shapes, invalid UTF-8, upstream HTTP errors, and
  truncated upstream bodies fail closed.
- The client receives a sanitized `gateway_stream_error` event followed by
  `[DONE]`; raw upstream errors are not exposed.
- Buffered, not-yet-safe text is discarded on an upstream failure rather than
  flushed, preventing a partial sensitive value from leaking.
- A downstream `CancelledError` is re-raised. Exiting the nested stream context
  closes the HTTPX response and stops upstream consumption.
- Per-request redaction counts are logged after stream termination.

## Other changes

- `task3/provider/mock_provider.py` adds `card-split-one-char`, `mixed`,
  `pii-end`, and deliberately malformed fixtures.
- `task3/scripts/consume.py` now assembles delta content, requires `[DONE]`,
  and supports `--assert-identical` for clean fixtures.
- The consumer remains directly runnable as a file from the repository root;
  it does not depend on package-import side effects.

## Files touched

- `task3/gateway/app.py`
- `task3/gateway/sse.py`
- `task3/provider/mock_provider.py`
- `task3/scripts/consume.py`
- `task3/tests/test_sse.py`
- `task3/README.md`
- `task3/PHASE0_DOCUMENTATION.md`
- `task3/PHASE2_DOCUMENTATION.md`

## Focused validation battery

```text
python -m pytest task3/tests/test_sse.py -q
..................                                                       [100%]
18 passed
```

These tests prove:

- UTF-8 reconstruction when every input byte arrives separately.
- CRLF event separation.
- Email, SSN, and card redaction when every character is a separate SSE frame.
- Byte-identical assembled output for clean content.
- PII at the end is flushed before the finish frame and sentinel.
- A missing sentinel is added exactly once.
- Usage frames are preserved.
- Invalid JSON, non-object payloads, invalid choices, invalid deltas, non-text
  content, and multi-choice bypass attempts fail closed.
- Two interleaved request-scoped guardrails cannot observe each other's text.
- Closing the downstream generator closes the upstream response context.
- Injected downstream cancellation propagates and closes upstream.
- Malformed upstream data becomes a sanitized error plus `[DONE]`.

## Live two-process evidence

Independent provider and gateway Uvicorn processes were run on ports 18601 and
18600. The following acceptance paths all exited zero:

```text
card-split-one-char -> assembled card replaced by [REDACTED], then [DONE]
plain --assert-identical -> exact clean fixture, then finish frame and [DONE]
mixed -> email, SSN, and card each replaced by [REDACTED], then [DONE]
malformed -> sanitized gateway_stream_error, then [DONE]
```

No validation process remained listening after the run.

## Acceptance result

- Parse frames and redact only delta text: **PASS**.
- One redactor instance per request: **PASS**.
- Emit only non-empty safe content: **PASS**.
- Flush held output before terminal sentinel: **PASS**.
- Terminal sentinel on normal, missing-sentinel, and error paths: **PASS**.
- Client cancellation closes upstream consumption: **PASS**.
- One-character card fixture redacted in assembled output: **PASS**.
- Clean assembled output byte-identical: **PASS**.
- Malformed frame handled without corrupting JSON or hanging: **PASS**.

## Phase boundary

Phase 2 implements the core live behavior. Phase 3 measures and proves latency,
throughput, and bounded memory under long and pathological streams. Phase 4
will finish reviewer-facing instructions, trade-offs, and clean-clone evidence.
