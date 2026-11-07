# Task 4 — Rate-Limiting and Model Fallback Router

Phases 0 and 1 are complete. The project currently provides the durable SQLite
foundation, deterministic provider fixtures, typed limiter/router contracts, and
a gateway endpoint with one sanitized error format. The limiter and fallback
behavior remain deliberate Phase 1 stubs; they are implemented in Phase 2.

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

The Phase 1 response identifies `primary`. No provider call occurs until Phase 2.

Run the controllable provider fixture separately when inspecting it:

```powershell
.\.venv\Scripts\python.exe -m uvicorn task4.providers.mock_provider:app `
  --host 127.0.0.1 --port 8201
```

The fixture routes are `/primary/v1/completions` and
`/secondary/v1/completions`. Select `normal`, `429`, `hang`, `slow`, or `500`
with `?mode=` or `TASK4_PRIMARY_MODE` / `TASK4_SECONDARY_MODE`.

## Validate Phases 0–1

```powershell
.\.venv\Scripts\python.exe -m pytest task4/tests -q
.\.venv\Scripts\python.exe -m compileall -q task4
git diff --check
```

`TASK4_DATABASE_PATH` selects the on-disk database. Its default is
`task4/data/usage.db`. Every connection enables WAL, a 5-second SQLite busy
timeout, and foreign keys. Initialization is idempotent.

## Phase boundary

The `TokenLimiter` currently allows all requests and `ModelRouter` always returns
a primary stub response. Phase 2 replaces those bodies with atomic sliding-window
reservation, reconciliation, provider calls, 3-second primary timeout, and
fallback. Describing those behaviors as complete before then would be misleading.
