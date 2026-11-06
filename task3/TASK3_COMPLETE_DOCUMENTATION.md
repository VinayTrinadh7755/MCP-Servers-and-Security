# Task 3 — Complete Implementation and Validation Documentation

## 1. Executive summary

Task 3 implements an LLM streaming gateway that proxies an OpenAI-compatible
Server-Sent Events (SSE) completion stream and redacts supported personally
identifiable information from generated text in real time.

The implementation detects:

- Dotted-domain email addresses.
- US Social Security numbers in `NNN-NN-NNNN` format.
- Card-like values containing 13–19 digits with optional spaces or hyphens.

Every detected value is replaced with `[REDACTED]` before it reaches the
client. The gateway does not accumulate the complete model response. It retains
only a bounded tail whose size is derived from the longest supported pattern.

The central correctness invariant is:

> Feeding text in arbitrary chunks produces exactly the same assembled output
> as feeding the complete text in one call.

The finished implementation includes a deterministic mock provider, a
network-free streaming redactor, incremental SSE parsing, request-scoped state,
sanitized error behavior, upstream cancellation, benchmarks, stress tests,
native Windows and Bash launchers, and clean-clone validation.

Final status:

- Task 3 tests: **85 passed**.
- Task 1 regression: **14 passed**.
- Task 2 regression: **54 passed**.
- Fresh-clone installation and Task 3 execution: **passed**.
- Dependency, compilation, whitespace, and repository-hygiene checks: **passed**.

## 2. Assessment requirements

The assessment asks for an LLM gateway endpoint that:

1. Routes text-generation requests to an LLM provider.
2. Streams the response back to the client.
3. Intercepts response deltas in real time.
4. Detects and redacts emails, SSNs, and credit-card-like values.
5. Handles patterns split across arbitrary stream boundaries.
6. Avoids buffering the complete response.
7. Minimizes Time To First Token (TTFT) and total latency.
8. Demonstrates efficient asynchronous streaming and bounded state management.

The implementation satisfies these requirements through bounded raw-text
carry-over rather than per-frame matching or whole-response accumulation.

## 3. High-level architecture

```text
                         one request-scoped pipeline

client
  |
  | POST /v1/chat/completions
  v
FastAPI gateway
  |
  | HTTPX streaming request
  v
OpenAI-compatible provider
  |
  | arbitrary byte chunks
  v
incremental UTF-8 decoder
  |
  | complete SSE events
  v
OpenAI delta parser
  |
  | choices[0].delta.content only
  v
bounded StreamRedactor
  |
  | safe text only
  v
SSE re-encoder -> StreamingResponse -> client
```

The mock provider and gateway run as separate processes. This proves that
streaming behavior is not an artifact of an in-process test transport.

## 4. Repository structure

```text
task3/
├── gateway/
│   ├── app.py                 FastAPI gateway and upstream lifecycle
│   ├── redactor.py            Bounded synchronous StreamRedactor
│   └── sse.py                 Incremental SSE decoder and delta guardrail
├── provider/
│   └── mock_provider.py       Deterministic OpenAI-shaped SSE provider
├── scripts/
│   ├── benchmark.py           Median TTFT, memory and throughput benchmark
│   ├── consume.py             Timestamped stream consumer and assembler
│   ├── run_both.ps1           Native Windows two-service launcher
│   └── run_both.sh            Bash two-service launcher
├── tests/
│   ├── test_phase0.py         Provider and fixture contracts
│   ├── test_redactor.py       Offline redactor correctness
│   ├── test_sse.py            SSE, integration, failure and cancellation
│   ├── test_streaming.py      1 MiB and 10,000-frame stress tests
│   └── test_performance.py    Benchmark and scaling guards
├── README.md                  Reviewer quick start and design summary
└── TASK3_COMPLETE_DOCUMENTATION.md
```

The earlier `PHASE0_DOCUMENTATION.md` through `PHASE4_DOCUMENTATION.md` files
remain as development history. This document supersedes them as the single
complete Task 3 reference.

## 5. Mock provider

`task3/provider/mock_provider.py` exposes:

- `GET /health`
- `POST /v1/chat/completions`

The completion endpoint returns OpenAI-style chat-completion deltas inside SSE
`data:` frames. A normal stream ends with:

1. A finish frame whose `finish_reason` is `stop`.
2. `data: [DONE]`.

Available fixtures include:

| Fixture | Purpose |
|---|---|
| `plain` | Clean progressively streamed text |
| `single` | Exactly one content frame |
| `empty` | No content deltas |
| `email` | Email redaction |
| `ssn` | SSN redaction |
| `card` | Card-like value redaction |
| `card-split-one-char` | One character per frame, including the card |
| `mixed` | Email, SSN and card in one response |
| `pii-end` | PII immediately before stream termination |
| `malformed` | Invalid JSON inside an SSE data frame |
| `disconnect` | Provider failure after a partial response |

The provider accepts bounded `chunk_size` and `delay_ms` controls. These make
pathological boundary layouts and timing behavior deterministic.

## 6. StreamRedactor design

### 6.1 Public interface

`task3/gateway/redactor.py` provides:

```python
redactor = StreamRedactor()
safe_text = redactor.feed(next_text_fragment)
final_text = redactor.flush()
```

It also exposes:

- `redaction_counts`: replacement totals by `email`, `ssn`, and `card`.
- `buffered_characters`: current retained raw-text state.

### 6.2 Pattern contracts

Each pattern is registered as a `PatternSpec` containing:

- Its name.
- A precompiled regex.
- The maximum number of characters it can consume.

Email support uses a bounded practical subset:

- Local part: 1–64 supported characters.
- Dotted DNS-style domain.
- Up to three domain labels.
- Top-level label containing alphabetic characters.

SSN support is exactly `NNN-NN-NNNN`, with digit boundaries.

Card support accepts 13–19 digits with an optional space or hyphen between
digits. Boundary checks reject a supported-length substring inside a longer
digit sequence.

### 6.3 Derived carry size

`MAX_PATTERN_LEN` is derived from the pattern registry:

```python
MAX_PATTERN_LEN = max(spec.max_length for spec in PATTERNS)
TAIL_LENGTH = MAX_PATTERN_LEN - 1
```

For the submitted patterns:

- `MAX_PATTERN_LEN`: **256 characters**.
- Normal retained tail: **255 characters**.

Adding a longer pattern automatically increases the carry. The implementation
does not contain an unrelated hardcoded buffer size that could silently become
incorrect when patterns change.

### 6.4 Feed algorithm

For each `feed(text)` call, the redactor:

1. Appends new text to its private raw buffer.
2. Calculates the nominal safe boundary by retaining 255 characters.
3. Scans for a match crossing that boundary.
4. Moves the boundary backward if emitting there would split a known match.
5. Redacts only the safe raw prefix.
6. Returns the redacted prefix and retains the raw tail.

Retaining raw text is important. A 13-digit value must not be permanently
redacted before six later digits arrive and turn it into a 19-digit value.

### 6.5 Flush algorithm

At the end of a valid stream, `flush()`:

1. Re-runs every pattern over the remaining raw tail.
2. Redacts complete matches located entirely in that tail.
3. Returns incomplete near-matches unchanged.
4. Clears the internal buffer.

Re-scanning is necessary because a complete value may never leave the retained
tail before the provider terminates.

### 6.6 Concrete boundary example

Assume the provider sends:

```text
frame 1: "The card is 4111-1111-"
frame 2: "1111-1111."
```

The first frame cannot be emitted immediately because future characters could
complete a supported card pattern. The redactor retains it. When the second
frame arrives, the combined raw text contains a complete card plus a terminating
boundary, so the assembled client output becomes:

```text
The card is [REDACTED].
```

The same output is produced when the complete sentence is supplied in one
call, in two chunks at any split offset, or one character at a time.

## 7. SSE processing

### 7.1 Incremental decoding

`SSEDecoder` accepts arbitrary byte chunks and uses Python's incremental UTF-8
decoder. A multibyte character split between network reads is reconstructed
safely. LF, CRLF, and CR line endings are normalized inside the private parse
buffer.

Only complete SSE event blocks leave the decoder. An incomplete event remains
bounded in decoder state until more bytes arrive.

### 7.2 Delta-only redaction

`DeltaGuardrail` parses every `data:` payload as JSON and validates the expected
OpenAI shape. Only this value is redacted:

```text
choices[0].delta.content
```

The gateway never applies regexes to raw SSE bytes or serialized JSON. That
avoids corrupting field names, identifiers, escaping, and framing.

Empty content frames carrying metadata such as `role: assistant` are preserved.
Usage frames with an empty `choices` array are also preserved.

### 7.3 Re-framing held content

The redactor may return an empty string because all current content remains in
the carry. In that case, no empty replacement frame is emitted.

Finish ordering is:

1. Flush and emit final safe content.
2. Emit the provider finish frame.
3. Emit exactly one `data: [DONE]` sentinel.

If a valid upstream stream ends without `[DONE]`, the gateway adds it. Events
after the first terminal sentinel are ignored.

### 7.4 Request isolation

Each incoming request creates a new:

- `SSEDecoder`
- `DeltaGuardrail`
- `StreamRedactor`

No carry buffer or counter is shared between requests. Tests interleave two
guardrails and prove that one request cannot observe text from another.

## 8. Error handling and cancellation

The gateway fails closed on:

- Invalid SSE JSON.
- Non-object data payloads.
- Invalid `choices` or `delta` structures.
- Non-text `delta.content`.
- Invalid UTF-8.
- Upstream HTTP/protocol failures.
- Truncated upstream response bodies.
- Unsupported multi-choice responses.

Multi-choice responses are rejected because safely supporting them requires one
independent redactor per choice. Forwarding uninspected secondary choices would
create a PII bypass.

On a stream error, the client receives:

1. A sanitized `gateway_stream_error` event.
2. `data: [DONE]`.

Raw provider exception details are not sent to the client. Buffered text that
has not been proven safe is discarded instead of flushed on an error.

If the client disconnects, `CancelledError` is re-raised. Exiting the nested
HTTPX stream context closes the upstream response and stops consuming provider
tokens. This prevents orphaned cost and resource usage.

## 9. Authentication and provider selection

The gateway defaults to the local mock provider:

```text
http://127.0.0.1:8101/v1/chat/completions
```

Configuration:

| Setting | Purpose |
|---|---|
| `TASK3_PROVIDER_URL` | Full upstream chat-completions URL |
| `TASK3_PROVIDER_API_KEY` | Optional server-side Bearer credential |
| `TASK3_CHUNK_SIZE` | Mock provider default content chunk size |
| `TASK3_PROVIDER_DELAY_MS` | Mock provider delay between chunks |
| `TASK3_GATEWAY_PORT` | Bash launcher gateway port |
| `TASK3_PROVIDER_PORT` | Bash launcher provider port |

The provider key is added by the gateway. Client authorization is not forwarded.
This separates client identity from the gateway's provider identity and avoids
credential confusion.

The mock provider is the submitted validation target because it is deterministic
and requires no paid account, credentials, internet access, or provider budget.
A real OpenAI-compatible service can be selected through the two provider
environment variables without modifying source.

## 10. Running Task 3

### 10.1 Install dependencies

From the repository root on Windows:

```powershell
py -3.11-64 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Linux/macOS:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

### 10.2 Start both services on Windows

```powershell
.\task3\scripts\run_both.ps1
```

Custom ports:

```powershell
.\task3\scripts\run_both.ps1 -GatewayPort 8200 -ProviderPort 8201
```

### 10.3 Start both services with Bash

```bash
PYTHON=.venv/bin/python bash task3/scripts/run_both.sh
```

Optional Bash ports:

```bash
TASK3_GATEWAY_PORT=8200 TASK3_PROVIDER_PORT=8201 \
  PYTHON=.venv/bin/python bash task3/scripts/run_both.sh
```

Both launchers stop their child processes when interrupted or when either
service exits.

### 10.4 Consume streams

In a second terminal:

```powershell
.\.venv\Scripts\python.exe task3\scripts\consume.py --fixture plain
.\.venv\Scripts\python.exe task3\scripts\consume.py --fixture card-split-one-char
.\.venv\Scripts\python.exe task3\scripts\consume.py --fixture mixed
```

Verify clean assembled output automatically:

```powershell
.\.venv\Scripts\python.exe task3\scripts\consume.py `
  --fixture plain --assert-identical
```

The consumer prints every SSE line with a millisecond timestamp, assembles
content deltas, and fails if the stream ends without `[DONE]`.

## 11. Automated validation

Run the entire Task 3 suite:

```powershell
.\.venv\Scripts\python.exe -m pytest task3\tests -q
```

Final result:

```text
85 passed
```

### 11.1 Provider tests

The provider suite verifies:

- OpenAI-shaped content deltas.
- Finish frame and terminal sentinel.
- Exact fixture reconstruction.
- Single-frame and empty responses.
- One-character card framing.
- Safe unknown-fixture fallback.

### 11.2 Offline redactor tests

The redactor suite verifies:

- Whole email, SSN, and card redaction.
- Compact, spaced, and hyphenated cards.
- Every card length from 13 through 19 digits.
- One-character-at-a-time equivalence.
- Every possible two-chunk split offset.
- Split equivalence on inputs longer than the carry window.
- PII at stream start and end.
- Adjacent PII with no separator.
- Correct per-type counters.
- Literal `[REDACTED]` preservation.
- Partial SSN and email preservation.
- Rejection of 12-digit and 20-digit card near-matches.
- Long clean documents remaining byte-identical.
- Reusable state after `flush()`.
- Explicit rejection of non-string input.

### 11.3 SSE and gateway tests

The streaming suite verifies:

- UTF-8 split at every byte boundary.
- CRLF event parsing.
- One-character email, SSN, and card frames.
- Exact clean assembled output.
- Flush ordering before finish and `[DONE]`.
- Missing-sentinel recovery.
- Usage and empty metadata-frame preservation.
- Malformed frame rejection.
- Multi-choice bypass rejection.
- Request-state isolation.
- Generator closure closing the upstream context.
- Explicit cancellation propagation.
- Sanitized error plus sentinel behavior.
- Exact server-side provider Bearer header.

### 11.4 Memory and performance tests

The hardening suite verifies:

- A 1 MiB boundary-free token remains exact and bounded.
- Peak retained state stays within a small multiple of `MAX_PATTERN_LEN`.
- 10,000 one-character SSE frames remain exact and bounded.
- Repeated pattern-like text does not accumulate.
- Benchmark output contains plausible median measurements.
- Doubling pattern-like input remains comfortably below quadratic scaling.

### 11.5 Live-process validation

Independent Uvicorn provider and gateway processes verified:

- One-character card input becomes `[REDACTED]`.
- Plain content remains byte-identical.
- Mixed content produces three redactions.
- Malformed provider output produces a sanitized error and `[DONE]`.
- Progressive SSE delivery occurs over actual TCP connections.
- Provider failure does not hang the client.

## 12. Benchmark and measurements

Run:

```powershell
.\.venv\Scripts\python.exe task3\scripts\benchmark.py
```

The script requires at least five runs and defaults to seven. It reports
medians rather than a noisy single measurement.

The isolated Phase 3 development run recorded:

```text
runs=7 statistic=median
baseline_ttft_ms=0.0063
guarded_ttft_ms=0.5610
compute_ttft_delta_ms=0.5547
frames_to_first_guarded_output=8
normal_carry_limit_chars=255
measured_peak_buffer_chars_1mib=255
regex_throughput_mib_s=1.16
```

The fresh-clone Phase 4 run recorded:

```text
runs=7 statistic=median
baseline_ttft_ms=0.0016
guarded_ttft_ms=0.1552
compute_ttft_delta_ms=0.1536
frames_to_first_guarded_output=8
normal_carry_limit_chars=255
measured_peak_buffer_chars_1mib=255
regex_throughput_mib_s=3.85
```

Timing varies with machine load, process state, filesystem caching, and security
software. The reproducible command is the source of truth, not a selected
number.

### 12.1 Correct TTFT interpretation

Compute overhead and content-release delay are different measurements.

The measured local compute delta is below Quilr's published `<50 ms`
enforcement reference. However, the conservative carry can still delay the
first safe content. With 32-character benchmark frames, safe output begins on
frame 8:

```text
modeled carry delay = (8 - 1) × upstream frame interval
```

At a 20 ms provider interval, this is approximately 140 ms of content delay,
even when guardrail compute time is below 1 ms. The submission states this
honestly rather than claiming that low CPU cost means zero TTFT impact.

## 13. Performance optimization decision

All regexes are precompiled. During hardening, a single named-alternation regex
was implemented and measured as an alternative to sequential substitutions.
It was rejected because:

1. It benchmarked worse on adversarial near-match text in the observed run.
2. It broke adjacent SSN-plus-email redaction. After the SSN match, the original
   boundary prevented the immediately adjacent email alternative from matching.

Sequential precompiled substitutions preserve correctness because replacing
the first item exposes the valid boundary of the next item. Correctness was
chosen over a speculative micro-optimization.

## 14. Security model

Security properties demonstrated by the implementation:

- Only parsed text content enters the regex engine.
- Unsupported structures fail closed.
- Request state is isolated.
- Buffered unsafe content is not emitted after provider failure.
- Errors are sanitized.
- The terminal sentinel is maintained on normal and error paths.
- Client cancellation closes upstream consumption.
- Provider credentials are server-side and are not read from client headers.
- Prompt and completion text are not written to application logs.
- Redaction counters can be logged without logging sensitive values.

Production controls that remain outside this focused assessment:

- Client authentication and authorization.
- HTTPS enforcement and certificate policy.
- Provider destination allow-listing and SSRF protection.
- Request-body, SSE-event, and concurrency limits.
- Secret-manager integration and key rotation.
- Distributed metrics, traces, alerting, and audit retention.
- Formal false-positive and false-negative evaluation datasets.

## 15. Detection limitations and trade-offs

Regex detects format, not semantic sensitivity. The submitted implementation
does not detect:

- Names.
- Postal addresses.
- Phone numbers.
- Medical record numbers.
- Arbitrary international identifiers.
- Card numbers written as words.
- Context-dependent sensitive statements.
- Every RFC-valid email form.

Possible false positives include a 13–19 digit business or inventory identifier
that resembles a card number.

The implementation intentionally does not require a Luhn-valid card number.
Adding Luhn validation would reduce false positives but allow invalid-yet-
sensitive test cards and account-like values to pass.

The email pattern supports a bounded dotted-domain subset. This makes the carry
length provable and avoids classifying `name@example` as an email, but unusually
deep valid domains fall outside the contract.

The normal 255-character carry is conservative because every pattern pays for
the longest email pattern. Per-pattern candidate tracking could reduce latency,
but would add state complexity and enlarge the correctness and audit surface.

## 16. Production evolution

A production version should combine deterministic patterns with a broader DLP
engine, classifier, or small specialized model. A classifier can recognize
context and additional entity types, but adds inference cost and tail latency.

A practical next iteration would:

1. Add body, event-size, timeout, and concurrency limits.
2. Require authenticated clients and HTTPS provider destinations.
3. Restrict outbound provider hosts.
4. Store provider credentials in a managed secret store.
5. Export TTFT, throughput, cancellation, error, and redaction-count metrics.
6. Add contextual and international PII detection.
7. Evaluate precision and recall against labeled data.
8. Load-test p50, p95, and p99 latency under concurrent streams.
9. Test against recorded streams from multiple OpenAI-compatible providers.

## 17. Clean-clone proof

A new temporary clone was created from commit `f5b7a6d`. A fresh Python 3.11
virtual environment was created, dependencies were installed only from
`requirements.txt`, all Task 3 tests ran, and the benchmark completed.

Observed evidence:

```text
85 passed in 4.87s
fresh benchmark completed
git status --short produced no output
f5b7a6d feat: complete Task 3 streaming PII guardrail
```

The temporary directory's absolute path was verified to be inside the operating
system temporary directory before it was removed.

The final documentation commit is:

```text
1b7cde5 docs: record Task 3 Phase 4 validation
```

## 18. Complete acceptance matrix

| Requirement | Result | Evidence |
|---|---|---|
| Proxy an LLM completion stream | PASS | Independent gateway and provider processes |
| Stream response progressively | PASS | Timestamped TCP consumer |
| Parse OpenAI SSE deltas | PASS | Incremental decoder and shape tests |
| Redact emails | PASS | Whole, split, one-character and live tests |
| Redact US SSNs | PASS | Whole, split and one-character tests |
| Redact 13–19 digit cards | PASS | Every length and separator form |
| Handle cross-frame matches | PASS | Every-offset equivalence suite |
| Do not buffer full response | PASS | 1 MiB peak carry of 255 characters |
| Preserve clean text | PASS | Byte-identical clean-document tests |
| Keep JSON/SSE valid | PASS | Delta-only parsing and re-encoding tests |
| Isolate concurrent requests | PASS | Interleaved guardrail test |
| Terminate streams correctly | PASS | Finish ordering and `[DONE]` tests |
| Handle malformed provider data | PASS | Sanitized error plus `[DONE]` |
| Cancel upstream on disconnect | PASS | Context closure and cancellation tests |
| Measure TTFT | PASS | Seven-run median benchmark |
| Measure regex throughput | PASS | Adversarial throughput benchmark |
| Prove bounded memory | PASS | 1 MiB and 10,000-frame tests |
| Document limitations | PASS | Detection and trade-off sections |
| Support reproducible review | PASS | Mock provider and clean-clone proof |

## 19. Final status

Task 3 is complete and submission-ready. The code demonstrates both properties
that are easy to claim but difficult to prove in streaming redaction systems:

1. Correct output is independent of provider chunk boundaries.
2. Memory retained by the redactor is independent of total response length.

The implementation, automated tests, live-process probes, benchmark, security
decisions, limitations, and clean-clone evidence are all included in the
repository.
