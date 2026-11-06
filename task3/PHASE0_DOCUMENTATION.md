# Task 3 / Phase 0 — Foundation

## Objective

Provide a mock LLM provider emitting OpenAI-shaped SSE deltas and a gateway
relaying those bytes progressively without buffering the complete response.

## Implemented

1. `task3/provider/mock_provider.py`
   - Provides chat-completions and health endpoints.
   - Emits delta JSON in SSE frames, a finish delta, then `[DONE]`.
   - Has plain, one-frame, empty, email, SSN, card, and disconnect fixtures.
   - Defaults the card fixture to one character per frame.
   - Accepts bounded chunk-size and delay controls.
2. `task3/gateway/app.py`
   - Opens the provider with `httpx.AsyncClient.stream`.
   - Relays `response.aiter_raw()` chunks immediately.
   - Keeps the upstream context alive through downstream consumption.
   - Adds anti-buffering response headers.
3. `task3/scripts/consume.py`
   - Prints every SSE line with elapsed milliseconds and flushes stdout.
4. Native PowerShell and Bash launchers start and clean up both services.
5. Ten automated checks cover fixture shape, terminal framing, exact content,
   unknown input, and adversarial splitting.

## Files touched

- `task3/__init__.py`
- `task3/provider/__init__.py`
- `task3/provider/mock_provider.py`
- `task3/gateway/__init__.py`
- `task3/gateway/app.py`
- `task3/scripts/consume.py`
- `task3/scripts/run_both.ps1`
- `task3/scripts/run_both.sh`
- `task3/tests/__init__.py`
- `task3/tests/test_phase0.py`
- `task3/README.md`
- `task3/PHASE0_DOCUMENTATION.md`
- `pyproject.toml`

## Validation evidence

```text
python -m pytest task3/tests -q
..........                                                               [100%]
10 passed
```

Independent Uvicorn processes were tested on ports 18500/18501. With an 8-byte
chunk and 40 ms provider delay, representative gateway arrival times were
2620.48, 2672.74, 2720.93, 2772.36, and 2819.48 ms. The roughly 40–52 ms gaps
prove progressive delivery instead of end-of-response batching. The first
absolute time includes local process/import startup; formal TTFT benchmarking
belongs to the finished task.

The live card fixture delivered individual character deltas. The disconnect
fixture delivered one partial frame, then the consumer exited promptly with
`httpx.RemoteProtocolError` and code 1 rather than hanging.

This records the historical Phase 0 pass-through behavior. Phase 2 supersedes
it: the current gateway converts an upstream failure into a sanitized stream
error followed by `[DONE]`.

## DONE WHEN assessment

- OpenAI-shaped streaming mock and terminal sentinel: **PASS**.
- One-character credit-card framing: **PASS**.
- Incremental gateway relay: **PASS**.
- Increasing client timestamps/no buffering: **PASS**.
- One-frame and empty responses: **PASS**.
- Provider failure truncates without hanging: **PASS**.

## Phase boundary

Phase 0 proves transport and timing only. Output remains unredacted by design,
so later redaction logic cannot conceal transport defects.
