# Task 1 — Phase 1: Strict Tool Contracts

## Status

Phase 1 is complete.

The MCP server now publishes exactly two tools with strict input contracts:

- `get_customer_record`
- `trigger_refund`

Both tools currently return deterministic stub responses. No customer datastore,
record lookup, refund processing, balance calculation, or refund persistence was
implemented. Those behaviors belong to Phase 2.

## Objective

Define the complete external contract for both assessment tools, publish that
contract through MCP `tools/list`, and reject malformed tool arguments at the
JSON-RPC boundary before adding business logic.

## Files Changed

### `task1/models.py`

Introduces the reusable field types and explicit Pydantic input models.

The shared field contracts are:

```text
CustomerId     -> strict string matching ^CUST-[0-9]{5}$
PositiveAmount -> strict float greater than zero
RefundReason   -> strict string with at least 10 characters
```

The explicit request models are:

```text
GetCustomerRecordInput
└── customer_id

TriggerRefundInput
├── customer_id
├── amount
└── reason
```

Both models inherit from `StrictToolInput`, which applies:

```python
ConfigDict(extra="forbid", strict=True)
```

This policy prevents:

- undeclared fields such as `is_admin` from being silently ignored;
- a string such as `"50.00"` from being coerced into a number; and
- malformed identifiers from reaching the tool implementation.

### `task1/server.py`

Registers the two tools and strengthens FastMCP's generated argument models.

The server now has three Phase 1 responsibilities in addition to its Phase 0
transport behavior:

1. register both tool names and descriptions;
2. apply strict validation and `extra="forbid"` to FastMCP's generated argument
   models; and
3. map Pydantic argument failures to JSON-RPC `-32602 Invalid params`.

The current stub behavior is intentionally simple:

```text
get_customer_record -> identifies the validated customer ID in a stub string
trigger_refund      -> echoes the validated ID, amount, and reason in a stub string
```

The handlers do not read or mutate application state.

### `task1/scripts/drive.py`

The SDK driver now supports three verification modes.

Default mode lists the tools and calls both valid stubs:

```powershell
.\.venv\Scripts\python.exe task1\scripts\drive.py
```

Schema mode prints the exact contracts visible to an MCP client:

```powershell
.\.venv\Scripts\python.exe task1\scripts\drive.py --dump-schema
```

Validation mode sends boundary and hostile inputs through a real SDK session:

```powershell
.\.venv\Scripts\python.exe task1\scripts\drive.py --validate
```

## Tool Contracts

### `get_customer_record`

Input:

| Field | Type | Constraint |
|---|---|---|
| `customer_id` | string | Must match `^CUST-[0-9]{5}$` |

Accepted example:

```json
{
  "customer_id": "CUST-12345"
}
```

Rejected examples:

```json
{"customer_id": "CUST-1234"}
{"customer_id": "CUST-ABCDE"}
{"customer_id": "CUST-12345\nCUST-99999"}
{"customer_id": 12345}
```

### `trigger_refund`

Input:

| Field | Type | Constraint |
|---|---|---|
| `customer_id` | string | Must match `^CUST-[0-9]{5}$` |
| `amount` | number | Must be greater than zero |
| `reason` | string | Minimum length of 10 characters |

Accepted example:

```json
{
  "customer_id": "CUST-12345",
  "amount": 10.5,
  "reason": "duplicate charge"
}
```

Rejected examples:

```json
{
  "customer_id": "CUST-12345",
  "amount": 0,
  "reason": "duplicate charge"
}
```

```json
{
  "customer_id": "CUST-12345",
  "amount": "50.00",
  "reason": "duplicate charge"
}
```

```json
{
  "customer_id": "CUST-12345",
  "amount": 10.5,
  "reason": "too short"
}
```

```json
{
  "customer_id": "CUST-12345",
  "amount": 10.5,
  "reason": "duplicate charge",
  "is_admin": true
}
```

## Design Decisions

### Interpret `CUST-XXXXX` as five decimal digits

The assessment does not explicitly state whether each `X` is numeric or
alphanumeric. This implementation chooses five digits:

```text
^CUST-[0-9]{5}$
```

This is the narrower and safer boundary for the assessment. It rejects ambiguous
identifiers rather than accepting a broader customer namespace silently. If a real
customer system allowed letters, the contract would be changed deliberately to an
anchored alphanumeric pattern after confirming the source-system rules.

### Anchor the complete identifier

Both `^` and `$` are present. This prevents a valid-looking ID followed by extra
characters or an embedded newline from passing validation.

### Reject extra arguments

Unexpected tool arguments are rejected instead of ignored. This matters at an
agent-to-tool boundary because injected or misspelled parameters should not reach
business logic unnoticed.

### Reject coercion

The models use strict types. In particular, `"50.00"` is not accepted as a refund
amount. The caller must send a JSON number that matches the published contract.

### Validation failures are protocol errors

Malformed arguments are not valid tool invocations. They return:

```text
JSON-RPC error code: -32602
Message: Invalid params
```

This differs from a future business failure. For example, a syntactically valid
customer ID that does not exist will be a valid tool invocation with an error tool
result in Phase 2. It should not be reported as malformed JSON-RPC parameters.

### Preserve the official SDK transport

The official SDK still owns stdio framing, JSON-RPC models, initialization, request
dispatch, and response serialization.

FastMCP 1.27.2 normally converts tool argument validation failures into
`CallToolResult(isError=True)`. The assessment explicitly requires standard
JSON-RPC error codes, so the server replaces the low-level `CallToolRequest`
handler with a narrow adapter:

- a Pydantic `ValidationError` becomes `ErrorData(code=-32602)`;
- a non-validation tool failure remains an error tool result; and
- a successful stub becomes a normal `CallToolResult`.

This adapter uses FastMCP's internal tool manager and low-level server handler
registry. Those APIs are version-sensitive, which is one reason the project pins
`mcp==1.27.2`. With more time, this behavior should be protected by dedicated raw
JSON-RPC integration tests before upgrading the SDK.

## Published JSON Schema

The schema returned by `tools/list` for `get_customer_record` includes:

```json
{
  "additionalProperties": false,
  "properties": {
    "customer_id": {
      "pattern": "^CUST-[0-9]{5}$",
      "type": "string"
    }
  },
  "required": ["customer_id"],
  "type": "object"
}
```

The schema returned for `trigger_refund` includes:

```json
{
  "additionalProperties": false,
  "properties": {
    "amount": {
      "exclusiveMinimum": 0,
      "type": "number"
    },
    "customer_id": {
        "pattern": "^CUST-[0-9]{5}$",
      "type": "string"
    },
    "reason": {
      "minLength": 10,
      "type": "string"
    }
  },
  "required": ["customer_id", "amount", "reason"],
  "type": "object"
}
```

The constraints are therefore visible to clients before a tool call is made. They
do not exist only as hidden Python checks.

## Validation Results

### Tool listing and valid stub calls

Command:

```powershell
.\.venv\Scripts\python.exe task1\scripts\drive.py
```

Observed result:

```text
['get_customer_record', 'trigger_refund']
get_customer_record isError=False
trigger_refund isError=False
DRIVER_EXIT=0
```

Result: **PASS**. Exactly two tools were listed, and both valid stub calls
succeeded.

### Boundary and adversarial validation

Command:

```powershell
.\.venv\Scripts\python.exe task1\scripts\drive.py --validate
```

Observed result:

```text
['get_customer_record', 'trigger_refund']
reason_exactly_10 isError=False
reason_9 error_code=-32602
zero_amount error_code=-32602
string_amount error_code=-32602
extra_field error_code=-32602
embedded_newline error_code=-32602
VALIDATION_EXIT=0
```

Result: **PASS**.

This proves:

- a 10-character reason is accepted;
- a 9-character reason is rejected;
- zero is rejected as an amount;
- a numeric string is not coerced;
- an unexpected field is rejected; and
- an ID containing an embedded newline is rejected.

### Schema inspection

Command:

```powershell
.\.venv\Scripts\python.exe task1\scripts\drive.py --dump-schema
```

Observed contract properties:

```text
tool count: 2
additionalProperties: false
customer_id pattern: ^CUST-[0-9]{5}$
amount exclusiveMinimum: 0
reason minLength: 10
SCHEMA_EXIT=0
```

Result: **PASS**.

### Python compilation

Command:

```powershell
.\.venv\Scripts\python.exe -m py_compile `
  task1\server.py `
  task1\models.py `
  task1\scripts\drive.py
```

Result: **PASS**. All Phase 1 Python files compiled without a syntax error.

### Phase 0 regression

The blank-line startup check was repeated after the Phase 1 changes.

Observed result:

```text
SERVER_EXIT=0
STDOUT_BYTES=0
STDERR_TRACEBACK=False
```

Result: **PASS**. Adding tools and protocol validation did not reintroduce stdout
contamination or shutdown errors.

## Phase 1 Completion Gate

- [x] Exactly two tools are published.
- [x] `get_customer_record` requires `customer_id`.
- [x] `trigger_refund` requires `customer_id`, `amount`, and `reason`.
- [x] Customer IDs require the complete `CUST-` prefix plus five digits.
- [x] Refund amounts must be greater than zero.
- [x] Refund reasons require at least 10 characters.
- [x] Extra fields are forbidden.
- [x] String-to-number coercion is rejected.
- [x] Both valid stub calls succeed.
- [x] Invalid arguments return JSON-RPC `-32602`.
- [x] The published schemas contain all required constraints.
- [x] The Phase 0 stdout and shutdown behavior still passes.

## Phase Boundary

Phase 1 intentionally does not include:

- customer fixture records;
- record lookup;
- unknown-customer behavior;
- balance checks;
- refund identifiers;
- refund persistence;
- idempotency handling;
- structured audit logs for tool calls; or
- automated pytest coverage.

Phase 2 may now implement the two tools against a small fixture store. It must
preserve the distinction established here:

- malformed arguments produce JSON-RPC `-32602`; and
- well-formed requests that fail a business rule produce an error tool result.
