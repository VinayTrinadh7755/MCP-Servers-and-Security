# Customer Operations MCP Server

## Phase delivery record

### Phase 0 - Foundation

Pinned the official Python MCP SDK and Pydantic, created the stdio server and SDK
driver, routed logs exclusively to stderr, and proved a clean initialize/list-tools
round trip with no tools registered yet.

### Phase 1 - Strict contracts

Added `get_customer_record` and `trigger_refund` schemas. Customer IDs require
`CUST-` plus five ASCII digits; refund amounts are strict positive numbers; reasons
require at least ten characters; and unknown fields are rejected.

### Phase 2 - Tool behavior

Implemented deterministic customer fixtures and refund processing with Decimal
arithmetic, customer-status checks, refund limits, stable success payloads, and
business failures returned as tool results rather than transport failures.

### Phase 3 - Protocol hardening

Mapped malformed tool arguments to JSON-RPC `-32602`, preserved request IDs,
verified unknown methods and malformed envelopes, and added a mechanical stdout
purity test with a contamination self-test proving the detector fails when it
should.

### Phase 4 - Finish and validation

Completed clean-clone instructions, logging and PII guidance, design decisions,
trade-offs, and integration tests using the official SDK. Final focused result:
**14 tests passed**.

A Python MCP server exposing strict customer-record and refund tools over stdio.
It uses the official MCP SDK, validates arguments before tool execution, separates
JSON-RPC protocol errors from business failures, and keeps all logs off the protocol
stream.

## Quick Start

Run these two PowerShell lines (four commands) from the repository root:

```powershell
py -3.11-64 -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest task1\tests -q; .\.venv\Scripts\python.exe task1\scripts\drive.py
```

Expected final output includes:

```text
14 passed
['get_customer_record', 'trigger_refund']
get_customer_record isError=False
trigger_refund isError=False
```

On Windows ARM64, `-3.11-64` explicitly selects an x64 Python 3.11 interpreter to
create `.venv`. The MCP
1.27.2 dependency tree includes `PyJWT[crypto]`, which pulls in `cryptography`; an
ARM64 wheel was unavailable in the development environment.

POSIX equivalent:

```bash
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest task1/tests -q && .venv/bin/python task1/scripts/drive.py
```

## Tools

### `get_customer_record`

Returns a fixture customer record.

Input:

```json
{
  "customer_id": "CUST-12345"
}
```

`customer_id` must match five ASCII digits exactly:

```text
^CUST-[0-9]{5}$
```

An existing customer returns a normal tool result. A structurally valid but unknown
customer returns `isError=true`, not a JSON-RPC parameter error.

### `trigger_refund`

Records a fixture refund and reduces the customer's remaining refundable balance.

Input:

```json
{
  "customer_id": "CUST-12345",
  "amount": 10.5,
  "reason": "duplicate charge"
}
```

Constraints:

| Field | Contract |
|---|---|
| `customer_id` | Strict string matching `^CUST-[0-9]{5}$` |
| `amount` | Strict number greater than zero |
| `reason` | Strict string from 10 through 1,000 characters |
| Extra fields | Rejected |

A successful response includes a unique ID shaped as
`RFND-[0-9A-F]{12}`. A refund equal to the available balance succeeds; a refund
above it returns an error tool result.

## Error Semantics

Malformed tool arguments are JSON-RPC protocol errors:

```json
{
  "error": {
    "code": -32602,
    "message": "Invalid params"
  },
  "id": 0,
  "jsonrpc": "2.0"
}
```

Examples include an invalid customer-ID format, a string amount, a non-positive
amount, a short or oversized reason, a missing field, and an undeclared field.

Business failures are successful JSON-RPC exchanges containing an MCP tool result
with `isError=true`:

- a valid customer ID that is absent from the store;
- a refund exceeding the customer's available balance.

Unknown tool names return JSON-RPC `-32601 Method not found`.

## Driver Commands

List tools and call both valid paths:

```powershell
.\.venv\Scripts\python.exe task1\scripts\drive.py
```

Inspect the schemas published through `tools/list`:

```powershell
.\.venv\Scripts\python.exe task1\scripts\drive.py --dump-schema
```

Run boundary and hostile validation cases:

```powershell
.\.venv\Scripts\python.exe task1\scripts\drive.py --validate
```

Run all fixture-backed business scenarios:

```powershell
.\.venv\Scripts\python.exe task1\scripts\drive.py --scenario all
```

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest task1\tests -v
```

The raw protocol tests launch the server as a subprocess and communicate with it
using newline-delimited JSON-RPC. They verify:

- stdout contains JSON-RPC only;
- invalid arguments return exactly `-32602`;
- request ID `0` is preserved;
- unknown tools return `-32601`;
- Arabic-Indic digits and embedded-newline IDs are rejected;
- validation details do not leak paths, tracebacks, or documentation URLs;
- unknown customers and over-balance refunds remain business-error results; and
- a validation error does not make the session unusable.

### Prove the purity test detects contamination

The server has an env-gated test-only fault injection branch. This command is
expected to fail because it injects a non-JSON stdout line:

```powershell
$env:MCP_SELFTEST = '1'
.\.venv\Scripts\python.exe -m pytest task1\tests\test_stdout_purity.py -q
Remove-Item Env:MCP_SELFTEST
```

The flag is unset by default and no application path enables it.

## Logging and PII

Stdout is exclusively the MCP transport. SDK and application diagnostics use
stderr.

Tool audit events are complete single-line JSON objects containing only:

```text
event
tool
customer_id
outcome
```

They intentionally exclude customer names, emails, plans, full records, balances,
and refund reasons. Both tools use the same `not_found` outcome for absent
customers.

## Design Decisions

### Five ASCII digits

The assessment writes `CUST-XXXXX` without defining the character class. This
implementation chooses five ASCII digits. `[0-9]` is deliberate; Python `\d` also
accepts Unicode decimal digits and would disagree with common JSON Schema clients.

### Validation occurs before the tool body

FastMCP-generated argument models are rebuilt with strict mode and
`extra="forbid"`. Validation failures are mapped to `-32602` by a narrow
`CallToolRequest` adapter. This adapter uses version-sensitive FastMCP internals,
which is why `mcp==1.27.2` is pinned.

### Business failures are tool results

A valid identifier that is not found and a refund blocked by current balance are
domain outcomes, not malformed JSON-RPC parameters.

### Decimal internal arithmetic

The assessment requires a float amount. The store converts it with
`Decimal(str(amount))` before subtraction. For production money movement, the API
should use integer minor units or a decimal-string contract instead.

### In-memory fixtures

The task asks for protocol and validation behavior, not persistence. A small fixture
store keeps the submission focused and reproducible.

## Trade-offs and What I Would Do With More Time

- **Persistence:** state disappears on restart and is not shared across processes.
  Production would use a transactional datastore.
- **Concurrency:** balance validation and mutation are not atomic. Production would
  use a transaction with a conditional update or row lock.
- **Idempotency:** repeated refund calls create separate refunds. A real refund tool
  needs a caller-supplied idempotency key with a uniqueness constraint.
- **Authentication:** intentionally omitted because Task 1 does not request it. In
  production, identity and authorization belong at the gateway and must be carried
  into the tool-call context for defense in depth.
- **Sub-cent amounts:** `10.555` is currently accepted, represented as `10.56`, and
  leaves `139.44` from `150.00`. Production should reject excess scale or define an
  explicit rounding policy.
- **Balance disclosure:** insufficient-balance errors currently include the
  available balance. This helps an authorized agent but exposes account state to an
  unauthenticated caller. Product policy should decide whether to return a generic
  message instead.
- **Reason storage:** the in-memory ledger stores the full free-text reason while
  logs exclude it. Production should define retention, classification, and masking
  rules before persisting agent-supplied text.
- **Portability:** tests use `pathlib`, `sys.executable`, explicit UTF-8, and text
  mode; the final suite passed on Windows x64 and Ubuntu ARM64.

## Project Layout

```text
task1/
|-- server.py
|-- models.py
|-- store.py
|-- scripts/
|   `-- drive.py
|-- tests/
|   |-- protocol.py
|   |-- test_stdout_purity.py
|   `-- test_validation.py
`-- README.md
```
