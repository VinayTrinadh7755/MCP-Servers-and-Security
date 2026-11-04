# Task 1 — Phase 2: Fixture-Backed Business Logic

## Status

Phase 2 is complete. The two MCP tools now operate against an in-memory fixture
store. Phase 3 has not started.

The key invariant is preserved:

- malformed arguments return JSON-RPC `-32602 Invalid params`;
- valid requests that fail a business rule return `CallToolResult(isError=True)`.

## Objective

Implement customer lookup and balance-aware refund behavior while keeping protocol
validation, business outcomes, audit logging, and store mutation clearly separated.

## Files

### `task1/store.py`

Provides three fictional customer fixtures, defensive lookup copies, an in-memory
refund ledger, UUID-based refund IDs, and balance mutation after successful refunds.

### `task1/server.py`

Replaces the Phase 1 stubs with fixture-backed tool behavior. It passes explicit
`CallToolResult` objects through the custom handler so business failures do not
become JSON-RPC errors. It also emits PII-safe audit events to stderr.

### `task1/models.py`

Caps refund reasons at 1,000 characters in addition to the existing 10-character
minimum. The generated MCP schema publishes both limits.

### `task1/scripts/drive.py`

Adds `--scenario all` for the Phase 2 business matrix and adds a 10,000-character
reason to `--validate`.

## Fixture Store

| Customer ID | Name | Plan | Initial balance |
|---|---|---|---:|
| `CUST-12345` | Avery Morgan | enterprise | `150.00` |
| `CUST-23456` | Jordan Lee | standard | `50.00` |
| `CUST-34567` | Riley Patel | starter | `25.00` |

Each record contains `customer_id`, `name`, `email`, `plan`, and `balance`. Emails
use the reserved `.test` domain. State is process-local and resets on restart.

`store.get()` returns a deep copy so callers cannot mutate fixture state directly.

## Refund Storage and Arithmetic

Successful refunds are appended to an in-memory list with:

```text
refund_id
customer_id
amount
reason
```

Refund IDs use `RFND-XXXXXXXXXXXX`, where the suffix is derived from UUID4.

Balances are stored as two-decimal strings. Calculations use `Decimal`, converting
the validated float with `Decimal(str(amount))`. This avoids importing a binary
float approximation directly into decimal arithmetic. A production financial API
would normally accept decimal strings or integer minor units, but the assessment
specifically requires a positive float.

After a successful refund, the amount is subtracted from the remaining balance.
Failed refunds do not mutate the customer or append a ledger entry.

## Tool Behavior

### `get_customer_record`

Known customer:

```json
{"customer_id":"CUST-12345"}
```

Returns `isError=false` with the complete record.

Well-formed unknown customer:

```json
{"customer_id":"CUST-99999"}
```

Returns:

```text
isError=true
Customer CUST-99999 was not found
```

This is a business result because the ID satisfies the published schema.

Malformed IDs return JSON-RPC `-32602` before the tool body runs.

### `trigger_refund`

Valid request:

```json
{
  "customer_id":"CUST-12345",
  "amount":10.5,
  "reason":"duplicate charge"
}
```

Returns `isError=false` with an amount formatted to two decimals and a refund ID.

If the amount exceeds the balance, the tool returns:

```text
isError=true
Refund amount exceeds the available balance of <balance>
```

A refund equal to the balance succeeds. A refund one cent above it fails.

## Error Classification

| Condition | Response |
|---|---|
| Invalid customer-ID format | JSON-RPC `-32602` |
| Zero or negative amount | JSON-RPC `-32602` |
| String amount | JSON-RPC `-32602` |
| Reason shorter than 10 | JSON-RPC `-32602` |
| Reason longer than 1,000 | JSON-RPC `-32602` |
| Extra argument | JSON-RPC `-32602` |
| Valid but unknown customer | Tool result, `isError=true` |
| Refund exceeds balance | Tool result, `isError=true` |
| Record found | Tool result, `isError=false` |
| Refund recorded | Tool result, `isError=false` |

## Audit Logging

Every executed tool call emits an INFO event to stderr. Example:

```json
{"customer_id":"CUST-23456","event":"tool_call","outcome":"insufficient_balance","tool":"trigger_refund"}
```

Events contain only the tool name, customer ID, and outcome. They deliberately
exclude customer names, emails, plans, complete records, refund reasons, and full
responses.

Possible outcomes are `found`, `not_found`, `insufficient_balance`, and
`recorded`. Both tools use `not_found` for the same customer-absence condition.

The audit logger has its own stderr handler with a `%(message)s` formatter and
propagation disabled. Each complete audit line is therefore valid JSON rather than
a JSON payload prefixed by a timestamp, level, or logger name.

## Commands

Run the Phase 2 matrix:

```powershell
.\.venv\Scripts\python.exe task1\scripts\drive.py --scenario all
```

Run strict validation:

```powershell
.\.venv\Scripts\python.exe task1\scripts\drive.py --validate
```

Inspect the published schemas:

```powershell
.\.venv\Scripts\python.exe task1\scripts\drive.py --dump-schema
```

Compile all Phase 2 files:

```powershell
.\.venv\Scripts\python.exe -m py_compile `
  task1\server.py task1\models.py task1\store.py task1\scripts\drive.py
```

## Validation Evidence

Business scenarios:

```text
known_customer isError=False
unknown_customer isError=True
refund_over_balance isError=True
valid_refund isError=False
refund_exact_balance isError=False
refund_one_cent_over isError=True
SCENARIO_EXIT=0
```

Protocol validation:

```text
reason_exactly_10 isError=False
reason_9 error_code=-32602
zero_amount error_code=-32602
string_amount error_code=-32602
extra_field error_code=-32602
embedded_newline error_code=-32602
reason_10000 error_code=-32602
VALIDATION_EXIT=0
```

The published `reason` schema includes:

```text
minLength: 10
maxLength: 1000
```

Audit and PII checks:

```text
AUDIT_LINES=6
avery.morgan@example.test=False
jordan.lee@example.test=False
riley.patel@example.test=False
TRACEBACK_PRESENT=False
```

Phase 0 regression and dependencies:

```text
SERVER_EXIT=0
STDOUT_BYTES=0
TRACEBACK_PRESENT=False
No broken requirements found.
```

## Implementation Issue Caught

The first scenario run exposed a missing `Decimal` import in `server.py`. Customer
lookup passed, but refund paths returned:

```text
Error executing tool trigger_refund: name 'Decimal' is not defined
```

The missing import was added and the complete matrix was rerun from a fresh server
process. All refund scenarios then passed. This demonstrates that the scenario
runner caught a real integration defect rather than checking only the happy path.

## Design Decisions

### Unknown customers are business failures

The request satisfies the schema; the lookup merely has no matching record. Calling
this `-32602` would incorrectly classify a domain outcome as malformed parameters.

### Successful refunds reduce the balance

Recording a refund without reducing the available balance would permit repeated
refunds beyond the fixture's original balance.

### Reasons are capped at 1,000 characters

The assessment specifies a minimum but no maximum. The cap prevents an unbounded
agent-controlled string from propagating into storage or downstream systems.

### Logs contain operational metadata only

The log answers which tool ran, for which fixture ID, and with what outcome without
turning stderr into a second customer-data store.

### Open product decisions

The current implementation behavior is documented but not treated as a final
product policy:

- A sub-cent amount such as `10.555` is accepted. The response and ledger show
  `10.56`, while the resulting balance is `139.44` from an initial `150.00`.
- An insufficient-balance error discloses the current balance to the caller.
- The refund ledger stores the complete reason even though audit logs exclude it.

These require explicit decisions before a production deployment.

## Known Limitations

- State disappears on server restart and is not shared between processes.
- Concurrent refunds are not protected by a transaction or lock.
- Repeated calls are not protected by an idempotency key.
- Task 1 contains no authentication or authorization.
- The public float contract is less suitable for money than decimal strings or
  integer minor units.
- The strict JSON-RPC adapter uses version-sensitive FastMCP internal hooks, which
  is one reason `mcp==1.27.2` is pinned.

## Completion Gate

- [x] Multiple deterministic customer fixtures exist.
- [x] Lookups return defensive copies.
- [x] Known customers return complete records.
- [x] Unknown customers return error tool results, not `-32602`.
- [x] Refunds above the balance return error tool results.
- [x] Valid refunds generate IDs and reduce balances.
- [x] Exact-balance refunds succeed.
- [x] One-cent-over refunds fail.
- [x] A 10,000-character reason returns `-32602`.
- [x] Every scenario emits an audit event.
- [x] Every complete audit line is valid single-line JSON.
- [x] Both tools use the same `not_found` audit outcome.
- [x] Fixture emails do not appear in stderr.
- [x] Customer names, plans, reason canaries, `@`, and balance values do not appear
  in audit stderr.
- [x] Five hundred generated refund IDs match `^RFND-[0-9A-F]{12}$` with zero
  collisions, and response IDs equal stored ledger IDs.
- [x] Unknown tools still return `-32601`.
- [x] Validation errors still return `-32602` and do not break the session.
- [x] No traceback appears in captured scenario output.
- [x] Phase 0 stdout isolation still passes.
- [x] Dependency integrity remains clean.

## Phase Boundary

Phase 2 intentionally excludes permanent pytest suites, the deliberate stdout
contamination self-test, persistent storage, concurrency control, authentication,
and refund idempotency.

Phase 3 may add permanent subprocess-based stdout-purity and protocol validation
tests. It must preserve the Phase 2 business behavior and PII-safe logging.
