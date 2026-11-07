# Task 4 — Complete Implementation Record

## Outcome

Task 4 implements an on-disk, token-aware sliding-window limiter and a resilient
two-provider completion router. Admission is atomic under concurrency, provider
work is timeout-bounded, and errors cross one sanitized boundary.

## Phase summary

### Phase 0 — Foundation

- Pinned `aiosqlite`; created an idempotent indexed schema.
- Enabled WAL and a 5-second busy timeout on every connection.
- Added deterministic normal, 429, hang, slow, and 500 provider fixtures.

### Phase 1 — Contracts

- Defined async limiter/router contracts and response value objects.
- Added `/v1/completions` and a stable gateway error envelope.
- Correlated success, client errors, and internal logs with request IDs.

### Phase 2 — Load-bearing behavior

- Implemented a 60-second window with a 50,000-token default cap.
- Used `BEGIN IMMEDIATE` for atomic eviction, usage read, and reservation insert.
- Added estimate-before-call and actual-usage reconciliation.
- Added a conservative 4,096-token default when `max_tokens` is omitted.
- Added 429/3-second-timeout fallback and an independent secondary timeout.
- Released reservations when neither provider produced a completion.
- Proved that timeout cancels the primary coroutine.

### Phase 3 — Hardening

- Proved tenant isolation, exact-boundary eviction, and bounded row count.
- Released reservations on client-task cancellation; abrupt process death leaves
  the estimate charged until normal window eviction.
- Added rate-limit and retry headers, request and tenant size bounds, strict
  provider response validation, and fail-closed malformed-response behavior.
- Kept hosts, upstream bodies, paths, exception types, and tracebacks out of
  client responses while retaining request-correlated server logs.

### Phase 4 — Finish

- Added Windows and POSIX two-service launchers.
- Documented the algorithm, configuration, failover table, and limitations.
- Added concurrency, failover, cancellation, isolation, eviction, and error tests.

## Design decisions

Reserve-then-reconcile prevents a large request from crossing the cap before the
limiter reacts. The estimate is `ceil(prompt characters / 4) + max_tokens`; a live
adapter should replace it with the selected model's tokenizer.

Failed calls release their reservation. That is tenant-fair, although a timed-out
primary may have incurred unseen cost. A strict cost gateway could charge a
conservative timeout amount instead.

Only 429 and timeout trigger fallback, matching the brief. Primary 500, transport,
and protocol failures fail closed rather than duplicating unknown failures.

SQLite is intentionally not presented as distributed infrastructure. It satisfies
the on-disk requirement but serializes writers and cannot coordinate multiple
hosts. A shared atomic store is the production replacement.

## Acceptance mapping

| Requirement | Implementation | Proof |
|---|---|---|
| 50,000 tokens/minute per tenant | sliding timestamp query | concurrency, boundary, isolation tests |
| Atomic admission | `BEGIN IMMEDIATE` | 60 simultaneous reservations |
| Accurate eviction | cutoff delete in transaction | bounded-row test |
| 429/3000ms fallback | `ModelRouter` | failover and cancellation tests |
| Bounded secondary | independent timeout | dual-hang test |
| Standard errors | `errors.py` and handlers | forbidden-string tests |
| On-disk SQLite | WAL database file | PRAGMA/schema tests |

## Defend this

- Why does `BEGIN IMMEDIATE` close the cap race?
- Why reserve `max_tokens` before generation?
- What happens when actual usage exceeds its estimate?
- How is primary cancellation proven?
- Why does primary 500 not trigger fallback?
- Where does this SQLite design stop scaling?
