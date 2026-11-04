# Task 1 — Phase 4: Reviewer Handoff

## Status

Phase 4 is complete. Task 1 is complete through all five planned phases.

This phase adds the reviewer-facing runbook, consolidates the design decisions and
trade-offs, and proves that the submission installs and runs in a fresh directory
with a new virtual environment.

## Objective

Make the submission understandable and runnable by a reviewer in under two minutes,
without relying on the development virtual environment or undocumented setup steps.

## Files Added or Changed

### `task1/README.md`

The final reviewer-facing document includes:

- project purpose;
- two-command Windows and POSIX setup paths;
- both tool contracts with example payloads;
- JSON-RPC versus business-error semantics;
- driver and test commands;
- stdout-isolation and self-test instructions;
- logging and PII policy;
- design decisions;
- production trade-offs;
- environment portability notes; and
- project layout.

### Root `README.md`

Adds a direct link to the Task 1 README so a reviewer can discover the submission
from the repository root.

### `task1/PHASE_4.md`

Records the completion work and clean-environment evidence from this phase.

## Reviewer Quick Start

From the repository root on Windows PowerShell:

```powershell
py -3.11 -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest task1\tests -q; .\.venv\Scripts\python.exe task1\scripts\drive.py
```

Expected output includes:

```text
14 passed
['get_customer_record', 'trigger_refund']
get_customer_record isError=False
trigger_refund isError=False
```

The equivalent POSIX commands are included in `task1/README.md`.

## Clean-Environment Verification

A disposable directory was created outside the repository. Only the submission
files were copied into it:

```text
requirements.txt
pyproject.toml
README.md
task1/
```

The existing development `.venv` was not copied. A new virtual environment was
created with Python 3.11 x64, and dependencies were installed solely from
`requirements.txt`.

### Fresh test result

```text
..............                                                           [100%]
14 passed in 9.79s
FRESH_TEST_EXIT=0
```

Result: **PASS**.

### Fresh driver result

```text
['get_customer_record', 'trigger_refund']
get_customer_record isError=False
trigger_refund isError=False
FRESH_DRIVER_EXIT=0
```

Result: **PASS**.

### Fresh dependency integrity

```text
No broken requirements found.
```

Result: **PASS**.

### Cleanup

The disposable directory was removed after verification:

```text
TEMP_EXISTS=False
```

Result: **PASS**.

## Documented Contracts

### `get_customer_record`

```text
customer_id: strict string matching ^CUST-[0-9]{5}$
```

### `trigger_refund`

```text
customer_id: strict string matching ^CUST-[0-9]{5}$
amount: strict number greater than zero
reason: strict string, 10 through 1,000 characters
extra fields: forbidden
```

Malformed arguments return JSON-RPC `-32602`. Unknown tools return `-32601`.
Unknown customers and over-balance refunds are business-error tool results.

## Final Design Decisions

### Use the official SDK

The server and normal driver use the official MCP Python SDK. Raw JSON-RPC exists
only in the test harness where wire-level assertions are required.

### Reserve stdout for MCP

Application and SDK logs use stderr. Permanent tests parse every captured stdout
line as JSON-RPC, and the env-gated self-test proves contamination is detected.

### Use ASCII customer IDs

`[0-9]` intentionally avoids Python `\d` accepting Unicode decimal digits while
clients interpret the published JSON Schema differently.

### Separate protocol and business errors

Schema failures are `-32602`. A valid request that cannot be fulfilled remains a
tool result. This gives clients a stable way to distinguish a malformed invocation
from a domain outcome.

### Use fixture-backed state

The assessment focuses on MCP transport, validation, and error handling. An
in-memory fixture store keeps the implementation bounded and reproducible.

### Log operational metadata without PII

Audit lines contain tool name, fixture customer ID, and outcome. They exclude names,
emails, plans, balances, complete records, and free-text refund reasons.

## Production Trade-offs

### Persistence

The store and refund ledger are process-local. Production requires a durable,
transactional datastore.

### Concurrency

Balance checking and mutation are not atomic. Concurrent refunds could overdraw the
fixture balance. Production requires a conditional update or locked transaction.

### Idempotency

Repeated refund calls create distinct refunds. Production requires a caller-supplied
idempotency key enforced by a uniqueness constraint.

### Authentication and authorization

Task 1 does not request authentication. Production identity and coarse authorization
belong at the MCP gateway, with identity context carried into the server for
defense-in-depth checks and audit correlation.

### Money representation

The required float is converted through `Decimal(str(amount))`. A production API
should accept integer minor units or a decimal string and define scale explicitly.

### Open product-policy decisions

The implementation documents but does not silently resolve these product choices:

- reject or round sub-cent refund amounts;
- disclose or hide the available balance in failure messages; and
- retain, mask, or avoid storing free-text refund reasons.

### SDK internals

The strict validation adapter uses FastMCP's internal tool manager and request
handler registry. `mcp==1.27.2` is pinned, and raw protocol tests protect upgrades.

## Known Environment Note

Development occurred on Windows 11 ARM64 using an x64 Python 3.11 virtual
environment. MCP 1.27.2 declares `PyJWT[crypto]`, which pulls in `cryptography`.
The ARM64 interpreter attempted a source build without a usable ARM64 Rust toolchain;
the x64 interpreter installed compatible wheels.

The test harness itself uses `pathlib.Path`, `sys.executable`, explicit UTF-8, and
text-mode subprocess pipes. A true Linux/macOS run remains recommended before a
production release.

## Final Completion Gate

- [x] Reviewer-facing Task 1 README exists.
- [x] Repository root links to the Task 1 README.
- [x] Setup and verification fit into two entered commands.
- [x] Both tool contracts and examples are documented.
- [x] Protocol and business-error semantics are documented.
- [x] Stdout isolation and the deliberate self-test are documented.
- [x] PII-safe audit behavior is documented.
- [x] Idempotency, concurrency, persistence, and authentication limits are explicit.
- [x] Open product-policy decisions are explicit.
- [x] A fresh virtual environment installs from `requirements.txt`.
- [x] All 14 tests pass in the fresh environment.
- [x] Both live tool calls succeed in the fresh environment.
- [x] `pip check` passes in the fresh environment.
- [x] The disposable verification directory was removed.

## Final Task 1 Documentation

- `PHASE_0.md` — environment, stdio foundation, and dependency setup
- `PHASE_1.md` — strict schemas and JSON-RPC validation
- `PHASE_2.md` — fixture-backed business logic and audit logging
- `PHASE_3.md` — raw protocol tests and stdout hardening
- `PHASE_4.md` — reviewer handoff and clean-environment verification
- `README.md` — final reviewer-facing runbook
