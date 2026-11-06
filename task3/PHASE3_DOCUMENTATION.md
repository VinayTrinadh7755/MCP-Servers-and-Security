# Task 3 / Phase 3 — Performance and Memory Hardening

## Objective

Provide reproducible numbers for guardrail TTFT and regex throughput, and prove
that retained redaction state remains bounded independently of stream length.

## Deliverables

### Benchmark command

`task3/scripts/benchmark.py` runs directly from a clean repository checkout:

```text
python task3/scripts/benchmark.py
```

It reports the median of seven runs for:

- Pass-through compute time to first emitted content.
- Guarded compute time to first safe emitted content.
- The compute delta between those paths.
- Frames consumed before guarded output becomes safe.
- Adversarial regex throughput in MiB/s.
- Derived carry limit and measured peak buffer over 1 MiB.

The script rejects fewer than five runs so a caller cannot accidentally present
a noisy single sample as evidence.

### Bounded-memory proof

`task3/tests/test_streaming.py` feeds a 1 MiB string containing no boundaries in
1 KiB pieces. It hashes emitted output incrementally instead of accumulating a
second full result, verifies exact equality, samples the internal buffer after
every feed, and asserts the peak stays below a small multiple of
`MAX_PATTERN_LEN`.

The same file also processes:

- 10,000 one-character OpenAI delta frames through `DeltaGuardrail`.
- 20,000 repeated near-card fragments split into awkward 17-character chunks.

Both paths verify exact emitted length and the same bounded carry property.

### Scaling guard

`task3/tests/test_performance.py` benchmarks repeated pattern-like text at two
input sizes. Doubling the input must remain comfortably below a quadratic 4x
time increase. The threshold is intentionally tolerant of shared CI machines
while still catching whole-history re-scanning.

## Recorded results

The isolated Phase 3 benchmark on the development Windows machine produced:

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

The benchmark uses 32-character frames for TTFT and 1 MiB of deliberately
pattern-like near-match text for throughput. Results vary by machine and load;
the script is the source of truth for a reviewer's environment.

## Interpreting the latency result

The approximately 0.55 ms number is guardrail computation, not end-to-end model
latency. It is below Quilr's published `<50 ms` enforcement reference on this
machine. The carry introduces a separate, fixed content-release delay:

```text
(frames needed before safe output - 1) × upstream frame interval
```

At 32 characters per frame, safe output began on frame 8. A provider interval
of 20 ms therefore models about 140 ms of content delay. Stating both values
avoids the misleading claim that low compute cost means zero TTFT impact.

## Optimization decision

All three patterns are precompiled. A single compiled named-alternation pass was
implemented and measured during Phase 3, then rejected because:

1. It reduced adversarial throughput in the observed run.
2. It broke adjacent SSN-plus-email redaction: after the SSN match, the original
   boundary prevented the immediately adjacent email alternative from matching.

Sequential precompiled substitutions preserve that invariant because replacing
the first item exposes the second item's boundary. Correctness took precedence
over a speculative micro-optimization.

## Files touched

- `task3/scripts/benchmark.py`
- `task3/tests/test_streaming.py`
- `task3/tests/test_performance.py`
- `task3/gateway/redactor.py`
- `task3/README.md`
- `task3/PHASE2_DOCUMENTATION.md`
- `task3/PHASE3_DOCUMENTATION.md`

## Validation result

```text
Focused Phase 3 tests: 5 passed
1 MiB peak carry:       255 characters
10,000 tiny frames:     exact output, bounded carry
Pattern-like stream:    exact output, bounded carry
Benchmark run count:    7, median reported
```

## Acceptance matrix

- Median TTFT with and without redaction: **PASS**.
- Fixed carry delay stated honestly: **PASS**.
- 1 MiB bounded-memory assertion: **PASS**.
- Regex throughput benchmark: **PASS**.
- One enormous boundary-free token: **PASS**.
- 10,000 tiny frames: **PASS**.
- Repeated pattern-like adversarial stream: **PASS**.
- Non-quadratic scaling guard: **PASS**.
- `<50 ms` reference discussed with correct caveat: **PASS**.

## Phase boundary

Phase 3 supplies performance and memory evidence. Phase 4 remains responsible
for the final reviewer narrative, precise detection limitations, trade-offs,
and clean-clone submission rehearsal.
