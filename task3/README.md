# Task 3 — Streaming PII Guardrail

Task 3 is complete. It provides a reproducible mock provider, a bounded
network-free `StreamRedactor`, and a streaming gateway that applies redaction
only to parsed OpenAI content deltas.

## Quick start

```powershell
.\task3\scripts\run_both.ps1
```

In a second terminal:

```powershell
.\.venv\Scripts\python.exe task3\scripts\consume.py --fixture plain
```

Linux/macOS can use `PYTHON=.venv/bin/python bash task3/scripts/run_both.sh`.
The gateway listens on `8100` and provider on `8101` by default.

Fixtures include `plain`, `single`, `empty`, `email`, `ssn`, `card`, `mixed`,
`pii-end`, `malformed`, and `disconnect`. `card-split-one-char` emits one
character per frame. Error fixtures prove the client receives a sanitized error
and terminal sentinel rather than hanging.

```powershell
.\.venv\Scripts\python.exe -m pytest task3\tests -q
```

## Configuration

- `TASK3_PROVIDER_URL`: full upstream chat-completions URL.
- `TASK3_PROVIDER_API_KEY`: optional server-side Bearer credential for a live
  OpenAI-compatible provider. Client authorization is not forwarded.
- `TASK3_CHUNK_SIZE`: provider default chunk size.
- `TASK3_PROVIDER_DELAY_MS`: provider delay between chunks.
- `TASK3_GATEWAY_PORT` and `TASK3_PROVIDER_PORT`: Bash launcher ports.
- PowerShell ports are `-GatewayPort` and `-ProviderPort` parameters.

The credential-free mock makes boundary splitting and timing deterministic. To
use a live OpenAI-compatible endpoint, set `TASK3_PROVIDER_URL` to its streaming
chat-completions URL and set `TASK3_PROVIDER_API_KEY` if it requires Bearer
authentication. Submitted validation uses the mock so reviewers need no
account, network access, or paid credentials.

## Phase 1 offline redactor

`task3.gateway.redactor.StreamRedactor` exposes two operations:

```python
redactor.feed(text)  # returns the prefix that is safe to emit
redactor.flush()     # redacts and returns the final held tail
```

It recognizes dotted-domain email addresses, US SSNs in `NNN-NN-NNNN` form,
and 13–19 digit card-like values with optional spaces or hyphens. Matches become
`[REDACTED]`, and `redaction_counts` reports totals by `email`, `ssn`, and
`card`. Pattern lengths are explicitly bounded; `MAX_PATTERN_LEN` is derived
from the pattern registry, and only `MAX_PATTERN_LEN - 1` characters normally
remain held between calls.

Run the focused validation:

```powershell
.\.venv\Scripts\python.exe -m pytest task3\tests\test_redactor.py -v
```

The email regex intentionally requires a dotted DNS-style domain and supports
up to three labels. This bounded practical subset avoids treating
`name@example` as PII and makes the maximum carry length provable.

## Phase 2 live guardrail

The gateway incrementally decodes SSE, validates the OpenAI delta shape, and
feeds only `choices[0].delta.content` to one request-scoped redactor. It never
runs regexes over JSON syntax. Held text is emitted before the finish frame and
the terminal `[DONE]` sentinel. Malformed frames fail closed with a sanitized
stream error followed by `[DONE]`; unsupported multi-choice responses are also
rejected so an unchecked secondary choice cannot bypass the guardrail.

```powershell
.\.venv\Scripts\python.exe task3\scripts\consume.py --fixture card-split-one-char
.\.venv\Scripts\python.exe task3\scripts\consume.py --fixture plain --assert-identical
```

## Phase 3 performance and memory evidence

Run the reproducible benchmark from the repository root:

```powershell
.\.venv\Scripts\python.exe task3\scripts\benchmark.py
```

The benchmark uses seven runs and reports medians. On the development Windows
machine, the recorded Phase 3 run measured:

- Pass-through compute TTFT: 0.0063 ms.
- Guarded compute TTFT: 0.5610 ms.
- Compute delta: 0.5547 ms.
- First guarded output after 8 frames of 32 characters.
- Peak retained buffer over a 1 MiB stream: 255 characters.
- Adversarial near-match regex throughput: 1.16 MiB/s.

These are local measurements, not universal service-level guarantees. The
compute delta sits below Quilr's published `<50 ms` enforcement reference, but
that comparison alone is incomplete: the conservative carry can add content
delay. With the benchmark's 32-character frames, first output requires eight
frames, or seven upstream frame intervals after the first frame arrives. For a
provider producing one such frame every 20 ms, the modeled content delay is
about 140 ms even though local guardrail computation is below 1 ms.

The carry is intentionally conservative. `MAX_PATTERN_LEN` is 256, so normal
retained state is at most 255 characters regardless of total response size.
Tests prove that bound over a 1 MiB boundary-free token, 10,000 one-character
frames, and repeated pattern-like text. Individually precompiled regexes are
applied sequentially because a single alternation both benchmarked worse and
failed the adjacent-PII invariant during development.

## Architecture and carry-over invariant

```text
client -> FastAPI gateway -> HTTPX stream -> provider
             |
             +-> SSE decoder -> delta.content -> StreamRedactor -> SSE encoder
```

The central invariant is: **chunked input produces exactly the same assembled
output as feeding the complete text in one call**. A character is emitted only
when no future character can make it part of a supported match. The redactor
therefore keeps a bounded raw tail of `MAX_PATTERN_LEN - 1` characters, scans a
safe prefix, and re-scans the final tail during `flush()`.

For example, a provider may split a card across frames as `4111-1111-` and
`1111-1111`. The first fragment remains in the carry instead of being emitted.
After the second fragment and a following boundary arrive, the combined value
is replaced with `[REDACTED]`. If the stream ends there, `flush()` performs the
same replacement before the finish frame and `[DONE]` are sent.

## Detection contract

The guardrail detects these format families:

- Dotted-domain email addresses with a 1-64 character local part and up to
  three DNS-style labels.
- US SSNs in `NNN-NN-NNNN` form.
- Card-like values containing 13-19 digits with optional spaces or hyphens.

Regex recognizes format, not meaning. A name, postal address, phone number,
medical identifier, international identity format, or card number written in
words passes through. A 13-19 digit business identifier may be redacted even if
it is not a payment card. The regex does not perform a Luhn check because that
would reduce false positives but allow invalid-yet-sensitive test or account
numbers through.

At end of stream, an incomplete near-match is emitted unchanged. That is the
precision-oriented interpretation of the contract: a partial value is not a
complete supported pattern. A recall-oriented deployment could redact or flag
near-misses, but that policy would create additional false positives and should
be selected with the customer's security team rather than hidden in code.

For broader production coverage, place a deterministic DLP engine, classifier,
or small specialized model in the path. Those approaches can recognize context
and more entity types, but add model cost, operational dependencies, and tail
latency. A practical deployment can combine fast deterministic patterns with a
selectively invoked classifier.

## Security and failure behavior

- Redaction runs on decoded `delta.content`, never raw JSON or SSE syntax.
- Every request owns separate decoder and redactor state; tenants cannot share
  carry buffers.
- Unsupported multi-choice responses fail closed instead of leaving secondary
  choices uninspected.
- Malformed JSON, invalid UTF-8, upstream protocol errors, and truncated streams
  produce a sanitized error event followed by `[DONE]`.
- Buffered unsafe text is discarded on upstream failure.
- Client cancellation exits the HTTPX stream context and stops upstream
  consumption.
- Response bytes are streamed; the complete model response is never retained.

This demonstration terminates TLS at the gateway and trusts the configured
provider URL. Production deployment should require HTTPS, restrict outbound
destinations, keep provider credentials in a secret manager, authenticate the
client, apply request-size and concurrency limits, and export redaction counts
without logging prompt or completion content.

## Validation

```powershell
.\.venv\Scripts\python.exe -m pytest task3\tests -q
.\.venv\Scripts\python.exe task3\scripts\benchmark.py
```

The suite includes every-offset equivalence tests, one-character PII frames,
clean byte-identical output, request isolation, cancellation, malformed frames,
10,000 tiny frames, a 1 MiB boundary-free stream, bounded memory, and a
non-quadratic scaling guard.

For a clean-clone rehearsal on Linux/macOS:

```bash
git clone <repository-url> task3-review
cd task3-review
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest task3/tests -q
.venv/bin/python task3/scripts/benchmark.py
```

## Trade-offs and what I would do next

The derived 255-character carry is simple, auditable, and memory-bounded, but
conservative: every pattern pays for the longest email pattern. Per-pattern
candidate tracking could release ordinary text earlier, at the cost of more
state and a larger correctness surface. Before production, I would add request
body and SSE-event size limits, configurable upstream timeouts, authentication,
metrics for TTFT and redaction counts, HTTPS destination allow-listing, and a
second detection layer for contextual and international PII. I would validate
those changes against recorded provider streams and load-test p95/p99 latency,
disconnect rates, and false-positive/false-negative datasets.
