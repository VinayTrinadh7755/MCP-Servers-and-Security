# Task 3 / Phase 4 — Submission Finish

## Objective

Turn the completed streaming guardrail into a reviewer-ready submission with
precise run instructions, architecture explanation, measured evidence, honest
limitations, production trade-offs, and a clean-clone rehearsal.

## Reviewer documentation completed

`task3/README.md` now provides:

- Windows and Bash launch paths.
- A credential-free mock-provider workflow.
- Configuration for a real OpenAI-compatible URL and optional server-side
  Bearer credential.
- An architecture diagram showing the byte stream, SSE decoder, delta-only
  redaction, and re-encoding path.
- The explicit correctness invariant: chunked input produces the same assembled
  output as whole input.
- A worked example where `4111-1111-` and `1111-1111` arrive in separate frames.
- Detection contracts for email, US SSN, and card-like values.
- Local TTFT, carry, peak-buffer, and throughput measurements.
- The distinction between compute overhead and carry-induced content delay.
- Failure behavior, cancellation, request isolation, credential handling, and
  malformed-stream behavior.
- Exact validation and clean-clone commands.
- Trade-offs and concrete production follow-up work.

## Detection limitations

The README explicitly states that regex detects format rather than meaning. The
implementation does not claim to detect names, addresses, phone numbers,
medical identifiers, spelled-out card numbers, arbitrary international formats,
or contextual sensitive information. It may redact a numeric business
identifier that happens to have a card-like format.

The chosen end-of-stream policy is also explicit: incomplete near-matches are
emitted unchanged because they do not satisfy a complete supported pattern.
This favors precision. A deployment prioritizing recall could redact or log
near-misses, but that policy belongs in a customer security decision rather
than an undocumented implementation detail.

## Live-provider configuration

Phase 4 added `TASK3_PROVIDER_API_KEY`. When configured, the gateway adds it as
a Bearer credential to the provider request. Client authorization is not
forwarded. This separates client identity from the gateway's provider identity
and allows the mock-to-live switch without embedding credentials in source.

An automated test proves the exact upstream header. Another test proves an
empty-content frame carrying assistant-role metadata is preserved.

## Clean-clone evidence

A fresh local clone was created under a new temporary directory from commit
`f5b7a6d`. No existing virtual environment or source-tree cache was reused.
Python 3.11 created a new `.venv`, and dependencies were installed only from
the repository's `requirements.txt`.

Commands equivalent to the following were executed:

```powershell
git clone . $freshDirectory
py -3.11-64 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest task3\tests -q
.\.venv\Scripts\python.exe task3\scripts\benchmark.py
git status --short
git log -1 --oneline
```

Observed result:

```text
85 passed in 4.87s
runs=7 statistic=median
baseline_ttft_ms=0.0016
guarded_ttft_ms=0.1552
compute_ttft_delta_ms=0.1536
frames_to_first_guarded_output=8
normal_carry_limit_chars=255
measured_peak_buffer_chars_1mib=255
regex_throughput_mib_s=3.85
f5b7a6d feat: complete Task 3 streaming PII guardrail
```

`git status --short` printed nothing. The temporary clone was removed after its
absolute path was verified to be inside the operating-system temporary
directory.

Benchmark values differ from earlier development runs because timing depends on
machine load, filesystem caching, and process state. Each reported result uses
the script's median of seven runs. The reproducible command, not a cherry-picked
number, is the submission's source of truth.

## Full validation status

- Task 3 tests in the final remediated working tree: **101 passed**.
- Task 3 tests in fresh clone: **85 passed**.
- Fresh dependency installation: **PASS**.
- Fresh benchmark execution: **PASS**.
- Clean cloned worktree: **PASS**.
- Direct-file benchmark command: **PASS**.
- Provider-key boundary test: **PASS**.
- Empty metadata-frame preservation: **PASS**.
- Python compilation: **PASS**.
- Dependency consistency: **PASS**.
- Whitespace validation: **PASS**.
- Task 1 regression: **14 passed**.
- Task 2 regression: **54 passed**.

## Files touched

- `task3/README.md`
- `task3/PHASE4_DOCUMENTATION.md`
- `task3/gateway/app.py`
- `task3/gateway/sse.py`
- `task3/tests/test_sse.py`
- Root `README.md`

## Final assessment

Task 3 satisfies the assessment's functional requirements and makes the two
non-obvious properties directly reviewable: boundary-independent redaction and
bounded memory. It reports latency without conflating compute time with content
release delay, and it states the regex system's limits rather than presenting it
as comprehensive DLP.
