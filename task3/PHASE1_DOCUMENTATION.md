# Task 3 / Phase 1 — Offline Stream Redactor

## Objective

Implement and exhaustively validate a synchronous `StreamRedactor` whose output
is identical whether input arrives whole, one character at a time, or at any
two-chunk boundary.

## Scope and phase boundary

Phase 1 is deliberately network-free. It builds the stateful redaction
algorithm independently of SSE parsing and HTTP cancellation. The Phase 0
gateway therefore remains pass-through; wiring the redactor into it is Phase 2.

## Implementation

### Public contract

`task3/gateway/redactor.py` provides:

- `StreamRedactor.feed(text) -> str`: accepts the next text fragment and
  returns only text that no future input can change.
- `StreamRedactor.flush() -> str`: re-scans and returns the remaining tail,
  then clears the buffer.
- `StreamRedactor.redaction_counts`: counts replacements by `email`, `ssn`,
  and `card`.
- `StreamRedactor.buffered_characters`: exposes retained state for bounded-memory
  validation.

### Pattern contracts

- Email: local part of 1–64 supported characters, `@`, then a dotted
  DNS-style domain of up to three labels. Maximum length is calculated from
  those structural constants.
- SSN: exactly `NNN-NN-NNNN`, with digit boundaries.
- Card: 13–19 digits with an optional space or hyphen between digits. Boundary
  checks reject a card-like substring inside a longer digit sequence.

All patterns live in a `PatternSpec` registry with their calculated maximum
match lengths. `MAX_PATTERN_LEN` is derived using `max()` over that registry;
the normal carry is `MAX_PATTERN_LEN - 1`. Import-time assertions reject an
invalid carry contract.

### Boundary algorithm

The redactor retains raw, not already-redacted, tail text. On each feed it:

1. Appends new text to the private buffer.
2. Computes the nominal safe boundary from the derived tail length.
3. Moves the boundary backward if it would bisect an observed match.
4. Redacts only the raw prefix that is safe to emit.
5. Retains the remaining raw tail for the next feed.

Retaining raw state is important. Replacing a 13-digit match immediately could
be wrong if six more digits arrive and turn it into a 19-digit card. The bounded
tail postpones that decision until future input can no longer extend it.

At end of stream, `flush()` re-runs all patterns over the tail, catches complete
PII located entirely there, clears state, and returns partial near-matches
unchanged.

## Files touched

- `task3/gateway/redactor.py`
- `task3/tests/test_redactor.py`
- `task3/README.md`
- `task3/PHASE1_DOCUMENTATION.md`

## Validation battery

The focused suite contains 50 passing test cases:

```text
python -m pytest task3/tests/test_redactor.py -v
============================= 50 passed =============================
```

It verifies:

- Whole-value redaction for email, SSN, compact cards, spaced cards, and
  hyphenated cards.
- The same output when every character is fed separately.
- Every possible two-chunk split offset for every PII family.
- Split-offset equivalence on inputs longer than the carry window, forcing
  genuine incremental emission before flush.
- Every supported card length from 13 through 19 digits with no separator,
  spaces, and hyphens.
- PII at stream start and PII found only during final flush.
- Adjacent SSN and email values with no separator.
- Exact per-type counters for mixed input.
- Clean documents remain byte-identical, including long documents emitted
  incrementally.
- Near-matches remain unchanged: 12 digits, 20 digits, partial SSN,
  single-label email, and a pre-existing literal `[REDACTED]`.
- Memory carry remains bounded after a large feed.
- Flush clears buffered state and the instance can process a subsequent stream.
- Non-string input fails explicitly with `TypeError`.

## Acceptance result

- Explicit, documented patterns: **PASS**.
- Derived and asserted maximum pattern length: **PASS**.
- Bounded carry-over: **PASS**.
- `feed(text) -> str`: **PASS**.
- `flush() -> str` with final re-scan and reset: **PASS**.
- Counters by PII type: **PASS**.
- Whole versus one-character card equivalence: **PASS**.
- Every-offset equivalence: **PASS**.
- False-positive/clean-text direction: **PASS**.
- Network-free deterministic tests: **PASS**.

## Final submission gate

```text
Task 3 complete suite: 60 passed in 2.84s
Task 1 regression:     14 passed in 22.14s
Task 2 regression:     54 passed in 18.20s
pip check:             No broken requirements found
compileall task3:      exit 0
git diff --check:      exit 0
```

An offline sanity probe processed 1.1 million clean characters, verified exact
output equality, and completed in 727.20 ms on the development Windows machine.
The derived normal carry limit was 255 characters. This is not presented as a
cross-machine benchmark; it is reproducible evidence that the implementation
does not accumulate the complete document.

## Known trade-off

Regex PII detection is intentionally scoped, not an exhaustive identity
classifier. The bounded three-label email form provides deterministic memory
and latency and reduces false positives, but exceptionally deep valid email
domains fall outside this Phase 1 contract. That limitation is explicit rather
than hidden behind an unbounded regex.
