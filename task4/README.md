# Task 4 — Rate-Limiting and Model Fallback Router

All phases are complete. The gateway provides a per-tenant 50,000-token sliding
minute, atomic SQLite reservations, and bounded primary-to-secondary failover.
The local provider fixtures make every scored path reproducible without credentials.

## Run

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn task4.app:app --host 127.0.0.1 --port 8200
```

In another terminal:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8200/v1/completions `
  -Headers @{'x-tenant-key'='tenant-a'} -ContentType application/json `
  -Body '{"prompt":"hello","max_tokens":50}'
```

The response identifies the provider, actual usage, and whether fallback occurred.

Run the controllable provider fixture separately when inspecting it:

```powershell
.\.venv\Scripts\python.exe -m uvicorn task4.providers.mock_provider:app `
  --host 127.0.0.1 --port 8201
```

The fixture routes are `/primary/v1/completions` and
`/secondary/v1/completions`. Select `normal`, `429`, `hang`, `slow`, or `500`
with `?mode=` or `TASK4_PRIMARY_MODE` / `TASK4_SECONDARY_MODE`.

## Validate

```powershell
.\.venv\Scripts\python.exe -m pytest task4/tests -q
.\.venv\Scripts\python.exe -m compileall -q task4
git diff --check
```

`TASK4_DATABASE_PATH` selects the on-disk database. Its default is
`task4/data/usage.db`. Every connection enables WAL, a 5-second SQLite busy
timeout, and foreign keys. Initialization is idempotent.

## Rate limiter

Admission estimates `ceil(len(prompt) / 4) + max_tokens`. An omitted
`max_tokens` safely defaults to 4,096. `BEGIN IMMEDIATE`
makes eviction, the tenant usage read, and reservation insert one atomic operation.
Successful calls reconcile the reservation to actual usage; total provider failure
releases it. Rows at or before `now - 60,000ms` expire, so the window slides rather
than resetting on a clock boundary.

Denied requests include `Retry-After`, `X-RateLimit-Limit-Tokens`, and
`X-RateLimit-Remaining-Tokens`.

Each request opens its own `aiosqlite` connection. The driver uses sqlite3's
default isolation level (`""`), but no DML precedes the explicit transaction, so
`BEGIN IMMEDIATE` is the transaction start. The concurrency suite adds a test-only
scheduling yield after the usage read; replacing `BEGIN IMMEDIATE` with plain
`BEGIN` then fails with `database is locked`, proving real lock contention.

## Failover decisions

| Primary outcome | Action | Accounting | Client result |
|---|---|---|---|
| Success | return primary | reconcile actual | `200`, no fallback |
| HTTP 429 | call secondary | reconcile secondary | secondary or sanitized `503` |
| exceeds 3 seconds | cancel, call secondary | reconcile secondary | secondary or sanitized `503` |
| other failure | fail closed | release | sanitized `503` |

The secondary has an independent configurable 3-second timeout. Tests assert that
the timed-out primary coroutine is cancelled, not abandoned.

## Error contract

Every failure returns `error.code`, `error.message`, and `error.request_id`.
Upstream bodies, provider hosts, file paths, exception names, and tracebacks remain
in request-correlated stderr logs and never enter client responses.

## Configuration

| Variable | Default |
|---|---|
| `TASK4_DATABASE_PATH` | `task4/data/usage.db` |
| `TASK4_TOKEN_LIMIT` | `50000` |
| `TASK4_PRIMARY_URL` | `http://127.0.0.1:8201/primary/v1/completions` |
| `TASK4_SECONDARY_URL` | `http://127.0.0.1:8201/secondary/v1/completions` |
| `TASK4_PRIMARY_TIMEOUT_SECONDS` | `3.0` |
| `TASK4_SECONDARY_TIMEOUT_SECONDS` | `3.0` |

## Trade-offs

SQLite satisfies the explicit on-disk requirement and makes the admission
transaction inspectable. It remains a single-node design: writers serialize,
multiple hosts cannot share the file, and production scale needs an atomic shared
store. Reconciliation can exceed the cap by one request when actual usage is above
the estimate. Releasing timed-out attempts is tenant-fair but can undercount unseen
provider work. Eviction stays on the admission path for submission simplicity;
high-volume production traffic should move cleanup off the hot path.

A client-cancelled handler releases its reservation. An abrupt process kill cannot
run cleanup, so the estimate remains charged until its 60-second row expires.
SQLite's default WAL auto-checkpoint remains enabled; sustained production traffic
should monitor WAL size and schedule explicit checkpoints if needed.

Track provider latency, 429s, timeouts, fallback rate, limiter denials, SQLite lock
time, and estimate-versus-actual drift.
