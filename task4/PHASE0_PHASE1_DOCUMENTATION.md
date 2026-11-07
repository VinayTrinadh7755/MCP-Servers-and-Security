# Task 4 — Phases 0 and 1 Completion Record

## Scope

This record covers only the first two Task 4 phases. Phase 0 establishes durable
SQLite and reproducible upstream fixtures. Phase 1 fixes the gateway contracts and
client-visible protocol without claiming that rate limiting or fallback is already
implemented.

## Phase 0 — Foundation

Implemented:

- pinned `aiosqlite==0.22.1` and included `task4*` in package discovery;
- an idempotent schema with an on-disk `token_usage` table;
- a hot-path `(tenant_key, ts_ms)` index;
- reservation/reconciliation status and unique request identity;
- WAL, `busy_timeout=5000`, and foreign keys on every connection;
- configurable `TASK4_DATABASE_PATH`, defaulting to `task4/data/usage.db`;
- ignored database, WAL, and shared-memory runtime artifacts;
- primary and secondary mock routes with normal, 429, hang, slow, and 500 modes.

The schema is intentionally ready for Phase 2's reserve-then-reconcile algorithm.
No premature limiter behavior is hidden in the persistence layer.

## Phase 1 — Structure

Implemented:

- `TokenLimiter.try_reserve()` and `reconcile()` async contracts;
- a `Decision` carrying admission, reservation id, usage, cap, and retry timing;
- `ModelRouter.complete()` plus explicit request/result value objects;
- `POST /v1/completions` with tenant, JSON, and payload validation;
- request correlation on success and error responses;
- one gateway error envelope: `error.code`, `error.message`, `error.request_id`;
- sanitized framework and unexpected-exception handlers;
- a startup lifecycle that initializes the configured on-disk database.

The Phase 1 stub allows every reservation and selects primary. This is an explicit
phase boundary, not an accidental incomplete behavior.

## Validation coverage

`task4/tests/test_phase0.py` proves:

- initialization can run twice;
- WAL persists on disk;
- the schema and tenant/timestamp index exist;
- two connections open concurrently with the expected busy timeout;
- deterministic mock modes return their intended status and provider identity.

`task4/tests/test_phase1.py` proves:

- limiter and router contracts expose the required fields;
- the happy-path endpoint returns the primary provider and correlation id;
- missing tenant identity, malformed JSON, non-object JSON, and invalid fields all
  use the same stable envelope;
- client-visible errors contain no traceback or library implementation names.

## Design decisions

1. Reservations and reconciled usage share one table and request id. This makes
   reconciliation an update instead of a second usage record and avoids accidental
   double counting.
2. Request parsing is performed inside the route instead of FastAPI parameters.
   That guarantees malformed JSON and validation failures use the gateway's stable
   envelope rather than FastAPI's default 422 shape.
3. Mock behavior is selectable per request for deterministic tests, with environment
   variables available for live demonstrations.
4. SQLite is deliberately on disk. An in-memory shortcut would not test WAL,
   cross-connection behavior, or the assessment's stated storage requirement.

## Files

- `task4/db/schema.sql`
- `task4/db/connection.py`
- `task4/providers/mock_provider.py`
- `task4/limiter.py`
- `task4/router.py`
- `task4/errors.py`
- `task4/app.py`
- `task4/tests/test_phase0.py`
- `task4/tests/test_phase1.py`
- `task4/README.md`

## Completion gate

Phases 0 and 1 are complete when the focused suite, repository regression suite,
bytecode compilation, dependency check, and whitespace check all pass from the
pinned environment. Phase 2 must not be represented as complete: atomic admission,
actual provider failover, timeout cancellation, and reconciliation logic are still
its work.
