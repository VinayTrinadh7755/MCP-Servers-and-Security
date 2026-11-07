# Task 3 — Submission Validation Report

Date: 2026-11-06 (America/Denver)

## Overall verdict

**NOT YET an unconditional submission-ready PASS.**

All objective protocol, concurrency, leak, logging, portability, launcher,
README, mutation, and coverage failures found during this run were remediated.
The remaining decision is Check 1: the 255-character conservative carry causes
50-, 150-, and 250-character clean responses to emit 100% of their content only
at flush. The implementation is memory-bounded but does not minimize TTFT for
short responses.

The validation request explicitly reserves that design decision for the owner.
The recommended resolution is a safe candidate-aware carry, not the unsafe
shortcut that emits all text merely because the current tail contains no `@`
or digit.

## Check 1 — Live short-response TTFT

Result: **FAIL — decision required.**

Setup: independent Uvicorn provider and gateway processes over TCP; clean
alphabetic content; provider chunks of 10 characters; 20 ms delay per provider
content frame.

Actual output:

```text
LEN=50 STATUS=200 FIRST_CONTENT_MS=731.09 TOTAL_MS=742.02 CONTENT_FRAMES=1 CHARS=50 FLUSH_FRACTION=1
LEN=150 STATUS=200 FIRST_CONTENT_MS=856.61 TOTAL_MS=857.73 CONTENT_FRAMES=1 CHARS=150 FLUSH_FRACTION=1
LEN=250 STATUS=200 FIRST_CONTENT_MS=1303.3 TOTAL_MS=1303.74 CONTENT_FRAMES=1 CHARS=250 FLUSH_FRACTION=1
```

| Clean content | First content | Total | Emitted only at flush |
|---:|---:|---:|---:|
| 50 characters | 731.09 ms | 742.02 ms | 100% |
| 150 characters | 856.61 ms | 857.73 ms | 100% |
| 250 characters | 1303.30 ms | 1303.74 ms | 100% |

Interpretation: retained memory is capped, but these responses are behaviorally
equivalent to whole-response buffering.

### Bound driver

The email regex can consume:

```text
64 local-part characters
+ 1 @ character
+ 191 domain characters (three 63-character labels and two dots)
= 256 characters
```

Therefore the global carry is 255 characters. The SSN maximum is 11. The card
maximum is 37 characters in this implementation (19 digits plus as many as 18
single-character separators), not 23.

### Alternative A — tighten email maximum to 128

A sound 128-character maximum requires changing the regex contract so it cannot
match more than 128 characters. Changing only the declared bound would create a
cross-chunk leak.

With a 127-character carry and one complete feed per measured response, the
flush fractions would be:

| Content | Approximate flush fraction |
|---:|---:|
| 50 | 100% |
| 150 | 84.7% |
| 250 | 50.8% |

Cost: small implementation change and test update, but narrower valid-email
coverage and no solution for very short responses.

### Alternative B — candidate-aware trimming

The proposed shortcut says a tail with no `@` and no digit can be emitted in
full. For the three alphabetic inputs, it would release 100% immediately.

That shortcut is unsafe. `ada` may arrive in one frame and
`@example.com` in later frames. Emitting `ada` immediately makes the later email
impossible to redact as one value.

A safe candidate-aware implementation must retain:

- Up to 64 trailing characters that could be an email local part before `@`.
- A bounded partial domain after `@`.
- Partial digit/separator prefixes for SSN and card patterns.

For an unbroken alphabetic run, a safe local-part-aware carry would retain up
to 64 characters. Approximate flush fractions would then be 100% for 50
characters, 42.7% for 150, and 25.6% for 250. Ordinary sentences with delimiters
would generally release sooner than those worst-case runs.

Cost: medium. It needs pattern-specific prefix-state logic plus the existing
every-offset, one-character, long-stream, and mutation batteries. It gives the
best latency improvement without reducing detection coverage.

### Recommendation

Implement safe candidate-aware trimming before submission. Do not implement the
no-`@`/no-digit shortcut as stated. If schedule forbids the change, ship the
current bounded implementation only with the explicit short-response table now
present in `task3/README.md`; that is honest but remains a weaker answer to the
TTFT criterion.

## Check 2 — Mutation controls

Result: **PASS with source-document caveat.**

The supplied validation text says “for each mutation” but contains no mutation
definitions. Four equivalent boundary mutations were therefore applied. Each
was reverted immediately, and the restored suite passed 101 tests.

### Mutation 1 — disable `stream:false` rejection

```text
1 failed, 100 passed
FAILED test_invalid_stream_controls_are_rejected_before_forwarding[{"stream":false}-requires stream=true]
```

### Mutation 2 — accept non-SSE upstream Content-Type

```text
1 failed, 100 passed
FAILED test_non_sse_provider_content_type_fails_closed
```

### Mutation 3 — bypass delta redaction

```text
6 failed, 95 passed
FAILED test_fifty_concurrent_mixed_and_one_character_card_streams_are_isolated
FAILED test_pii_split_one_character_per_sse_frame[email]
FAILED test_pii_split_one_character_per_sse_frame[ssn]
FAILED test_pii_split_one_character_per_sse_frame[card]
FAILED test_pii_at_end_is_flushed_before_finish_and_sentinel
FAILED test_request_scoped_instances_cannot_mix_tenants
```

### Mutation 4 — share one redactor between requests

```text
4 failed, 97 passed
FAILED test_fifty_concurrent_mixed_and_one_character_card_streams_are_isolated
FAILED test_clean_content_is_byte_identical_when_assembled
FAILED test_request_scoped_instances_cannot_mix_tenants
FAILED test_ten_thousand_one_character_frames_remain_bounded_and_exact
```

Restored result:

```text
101 passed in 7.16s
```

Interpretation: all four controls are guarded; the two PII-leak mutations are
detected by permanent tests, including a real TCP test.

## Check 3 — TCP concurrency and isolation

Initial result: **FAIL.** Final result after remediation: **PASS.**

Initial output with one HTTPX client per request:

```text
WALL 46.533
FAILURES 35
```

Diagnosis: constructing and closing a separate HTTPX client and pool for every
request collapsed under 50-way Windows concurrency. The gateway returned
sanitized stream errors for 35 requests.

Remediation: one lifespan-managed shared HTTPX client/pool; decoder, guardrail,
redactor, carry, and counters remain request-scoped.

Final output:

```text
kind=mixed requests=50 failures=0 wall_s=0.461
kind=card-split requests=50 failures=0 wall_s=0.403
```

Permanent test:

```text
task3/tests/test_live_concurrency.py::test_fifty_concurrent_mixed_and_one_character_card_streams_are_isolated PASSED
```

It asserts no raw PII, no foreign request marker, exact assembled output, no
missing sentinel, stable per-request counter groups, no hangs, and no 500s.

## Check 4 — Protocol and upstream boundaries

Result after remediation: **PASS.**

| Probe | Actual behavior | Permanent test |
|---|---|---|
| `stream:false` | HTTP 400 before provider call | Yes |
| Non-boolean `stream` | HTTP 400 | Yes |
| `n:2` | HTTP 400 before provider call | Yes |
| Unknown field | Preserved and forwarded; `stream:true` injected | Yes |
| Body/query/header provider URL influence | None; destination comes only from `TASK3_PROVIDER_URL` | Code boundary; query forwarding removed |
| HTTP 200, non-SSE Content-Type | Sanitized error plus `[DONE]` | Yes |
| SSE `: ping` | Preserved | Yes |
| SSE `event:` without data | Preserved | Yes |
| Content after `[DONE]` | Discarded | Yes |
| Provider sends no frames | Default 30 s read timeout | Live shortened-timeout probe |

Live shortened-timeout output:

```text
STATUS=200 ELAPSED_MS=345.28 ERROR_EVENT=True DONE=True
```

The probe set `TASK3_UPSTREAM_READ_TIMEOUT=0.2`; production default is 30.0 s.

## Check 5 — PII and credential log hygiene

Result: **PASS.**

Canaries:

- Card: `4999999999999999`
- SSN: `987-65-4321`
- Email: `CANARY7f3a@example.com`
- Provider key: `KEY_SENTINEL_9d82c1`

Actual summary:

```text
RESPONSE_STATUS=200 REDACTIONS=3 KEY_HITS=0
ERROR_RESPONSE_KEY_HITS=0
gateway.out: all canaries 0 hits
gateway.err: all canaries 0 hits
provider.out: all canaries 0 hits
provider.err: all canaries 0 hits
benchmark.out: all canaries 0 hits
REPO_ARTIFACT_HITS=0
CANARY_TEMP_REMOVED
```

Interpretation: content and provider credentials do not enter logs, benchmark
output, error responses, or repository test/cache artifacts.

## Check 6 — Benchmark stability, scaling and profile

Result: **PASS after README correction.**

Five independent benchmark-process results:

```text
RUN 1 baseline=0.001200 guarded=0.152800 delta=0.151600 throughput=3.886055
RUN 2 baseline=0.001500 guarded=0.150000 delta=0.148500 throughput=3.848042
RUN 3 baseline=0.001500 guarded=0.150300 delta=0.148800 throughput=3.842353
RUN 4 baseline=0.001200 guarded=0.150000 delta=0.148800 throughput=3.820051
RUN 5 baseline=0.001300 guarded=0.146500 delta=0.145200 throughput=3.816048
```

```text
baseline median=0.001300 min=0.001200 max=0.001500 spread=23.08%
guarded median=0.150000 min=0.146500 max=0.152800 spread=4.20%
delta median=0.148800 min=0.145200 max=0.151600 spread=4.30%
throughput median=3.842353 min=3.816048 max=3.886055 spread=1.82%
```

Raw scaling:

```text
131072 bytes median=0.032902 s
262144 bytes median=0.065729 s
524288 bytes median=0.132158 s
```

Doubling input approximately doubles time (2.00x and 2.01x), supporting linear
rather than quadratic behavior.

Profile and isolated component timing:

```text
three_substitutions median_s=0.126850
boundary_scan median_s=0.133969
buffer_slicing median_s=0.000174
```

cProfile attributed 0.126 s to 771 regex `subn` calls and the remaining major
cost to `feed`, where boundary `finditer` iteration occurs. Buffer slicing is
negligible. The honest description is: fast enough for ordinary chat-scale
chunks on this machine, but both regex substitution and boundary scanning need
work for high-volume bulk text.

README decision: quote a median plus observed range, not one historical point.
The README now does so.

## Check 7 — Test and fixture coverage

Result: **PASS after remediation.**

```text
101 tests collected
```

All node IDs, grouped by file with a one-line behavior description, are in
`task3/TEST_CATALOG.md`.

All original eleven provider fixtures are now referenced by permanent tests.
The additional configurable `hang` fixture is also tested.

### Section 18 acceptance mapping

| Acceptance row | Permanent evidence | Manual-only? |
|---|---|---|
| Proxy LLM stream | Live concurrency test | No |
| Stream progressively | Timestamped live observation | **Yes** |
| Parse OpenAI SSE | `test_sse.py` | No |
| Redact emails | Redactor and SSE tests | No |
| Redact SSNs | Redactor and SSE tests | No |
| Redact cards | Redactor, SSE and live tests | No |
| Cross-frame matches | Every-offset and one-character tests | No |
| Bounded total memory | 1 MiB and 10,000-frame tests | No |
| Preserve clean text | Redactor and SSE tests | No |
| Keep JSON/SSE valid | SSE tests | No |
| Isolate concurrent requests | Live 100-stream test | No |
| Terminate streams | Sentinel tests | No |
| Malformed provider data | Fail-closed tests | No |
| Cancel upstream | Cancellation/context tests | No |
| Measure TTFT | Benchmark test plus live measurement | No |
| Measure throughput | Performance test | No |
| Prove bounded memory | Streaming tests | No |
| Document limitations | Documentation inspection | **Yes** |
| Reproducible review | WSL clean-clone run | **Yes** |

## Check 8 — WSL Ubuntu ARM64

Result: **PASS.**

Platform observed:

```text
platform linux -- Python 3.14.4 -- ARM64 WSL Ubuntu
101 passed in 3.00s
test_decoder_handles_every_utf8_byte_boundary_and_crlf PASSED
```

Linux benchmark:

```text
baseline_ttft_ms=0.0013
guarded_ttft_ms=0.0870
compute_ttft_delta_ms=0.0857
frames_to_first_guarded_output=8
measured_peak_buffer_chars_1mib=255
regex_throughput_mib_s=6.38
```

Live WSL stream:

```text
data: ... "The test card is [REDACTED] and must eventually be redacted."
data: ... "finish_reason":"stop"
data: [DONE]
```

Foreground PTY Ctrl-C output showed both Uvicorn services shutting down, and:

```text
WSL_FOREGROUND_CTRL_C_CHILDREN_CLEAR
```

The UTF-8 byte-split and CRLF event-parsing behavior is identical on Windows and
Linux.

## Check 9 — README commands and launchers

Result: **PASS after documentation remediation.**

- Command blocks counted: 11 (3 root README, 8 Task 3 README).
- Ran: 11.
- Succeeded: 11 in their documented context.

Remediations:

1. Windows launcher command now uses process-scoped
   `-ExecutionPolicy Bypass`; the previous exact command was blocked by Windows.
2. Root Task 3 block no longer tries to start a blocking launcher and then run a
   consumer in the same terminal.
3. The literal `<repository-url>` block was replaced by a self-cleaning local
   `mktemp` clone.

Windows custom-port and cleanup evidence:

```text
WINDOWS_CUSTOM_PORTS gateway=200 provider=200
WINDOWS_TASK3_PROCESSES_CLEAR
WINDOWS_CUSTOM_PORTS_CLEAR
```

WSL custom-port and cleanup evidence:

```text
WSL_CUSTOM_PORTS gateway=200 provider=200
WSL_FOREGROUND_CTRL_C_CHILDREN_CLEAR
```

## Check 10 — Repository hygiene and documentation layout

Result: **PASS with layout recommendation.**

Tracked repository totals at measurement time:

```text
TRACKED_MARKDOWN_FILES=16
TRACKED_MARKDOWN_LINES=3237
TRACKED_FILES=64
```

The literal recursive PowerShell Markdown command also traversed `.venv` and
encountered package symlink/path-resolution errors, so it is not a reliable
repository-documentation metric. The tracked-file calculation above is the
meaningful result.

`git grep` found only benign uses of words such as “secret” in security
documentation and a provider-key test fixture. It found no checked-in Windows
user path, Vinay identity, AppData path, password, or `sk-...` credential.

Recommendation for all four tasks:

```text
README.md                         concise repository index
taskN/README.md                   reviewer quick start
taskN/TASKN_COMPLETE_DOCUMENTATION.md  one authoritative deep document
taskN/docs/history/               optional phase notes, outside the reviewer path
```

Apply this layout consistently before Task 4 adds documentation. Do not keep
five phase files beside the two reviewer-facing documents.

## Security findings and remediations

1. `stream:false` and `n:2` were forwarded. Fixed: rejected before provider
   access.
2. Client query parameters influenced the provider URL query. Fixed: provider
   destination is configuration-only.
3. Non-SSE HTTP 200 responses were not rejected. Fixed: strict upstream media
   type validation.
4. Per-request HTTPX clients collapsed under concurrency. Fixed: lifespan-managed
   shared pool with request-scoped guardrail state.
5. No runtime PII or provider-key log leak was found.
6. The current fixed carry is a TTFT weakness, not a PII leak.

## Coverage gaps

- The exact mutation definitions were absent from the supplied document; four
  equivalent mutations were used and all were guarded.
- Progressive inter-frame timing remains a measured manual live observation,
  not a permanent timing-sensitive test, to avoid flaky CI.
- Documentation quality and clean-clone reproducibility necessarily retain a
  manual inspection/execution component.

## README corrections made

- Replaced historical point benchmarks with five-process median and range.
- Added the live 50/150/250-character flush table.
- Replaced “complete response is never retained” with the accurate bounded-state
  statement and short-response caveat.
- Documented the actual configurable 30-second read timeout.
- Corrected current test count to 101.
- Corrected Windows execution-policy instructions.
- Replaced the non-executable repository URL placeholder.

## Final decision required

All remediable failures found in this validation run are cleared. The repository
is clean and cross-platform tests pass. Task 3 should be called submission-ready
only after the owner chooses one of:

1. Implement safe candidate-aware carry trimming (recommended).
2. Accept the current fixed carry and submit with the now-honest TTFT limitation.

The unsafe “emit everything when no `@` or digit is currently present” shortcut
should not be selected.
