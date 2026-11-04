# Task 1 — Phase 3: Protocol Hardening and Stdout Isolation

## Status

Phase 3 is complete. Phase 4 has not started.

The project now has permanent raw-stdio integration tests proving that:

- every server stdout line is valid JSON-RPC;
- malformed tool arguments return exactly `-32602`;
- unknown tools return exactly `-32601`;
- request ID `0` is preserved;
- business failures remain tool results rather than protocol errors;
- validation errors do not break the session;
- validation details do not expose stack traces, paths, or documentation URLs; and
- the purity test fails when deliberate stdout contamination is enabled.

## Objective

Mechanically prove the protocol and stdout properties that were previously checked
with ad-hoc commands. The tests launch the real server as a subprocess and exchange
raw newline-delimited JSON-RPC frames rather than relying on SDK normalization.

## Files Added or Changed

### `task1/tests/protocol.py`

Defines `RawMCPClient`, a small test-only subprocess harness.

It:

1. launches `task1/server.py` with the active virtual-environment interpreter;
2. owns stdin, stdout, and stderr independently;
3. sends raw JSON-RPC objects as UTF-8 JSON lines;
4. performs the MCP initialization handshake;
5. preserves every raw stdout line for later inspection;
6. supports requests with an explicit ID, including `0`;
7. closes stdin and waits for clean server shutdown; and
8. kills the subprocess only if it fails to exit within five seconds.

The harness intentionally avoids `ClientSession` for protocol assertions. An SDK
client may normalize an error response before the test can inspect the actual wire
object.

### `task1/tests/test_stdout_purity.py`

Starts a real server and mixes several paths in one session:

- initialization;
- `tools/list`;
- a malformed refund call; and
- a validly shaped request that produces a business failure.

After shutdown, the test parses every captured stdout line with `json.loads()` and
asserts `jsonrpc == "2.0"`. It also confirms stderr contains no traceback.

### `task1/tests/test_validation.py`

Exercises strict validation over raw JSON-RPC and asserts exact response classes and
codes.

Permanent cases include:

- short customer ID;
- customer ID containing an embedded newline and a second ID;
- Arabic-Indic digits;
- zero amount;
- string amount;
- nine-character reason;
- reason longer than 1,000 characters;
- unexpected `is_admin` argument;
- missing arguments;
- unknown tool;
- unknown customer business failure;
- over-balance refund business failure; and
- a valid call immediately after a validation failure in the same session.

### `task1/server.py`

Adds a deliberate test-only contamination branch:

```text
MCP_SELFTEST=1
```

When enabled, the server writes this non-JSON line directly to file descriptor 1:

```text
MCP_SELFTEST_STDOUT_CONTAMINATION
```

The branch is off by default. It exists to prove that the stdout-purity test detects
real contamination instead of passing regardless of server output.

## Why Raw Stdio Testing Matters

For a stdio MCP server, stdout is the protocol transport. A single banner, debug
message, warning, or accidental `print()` can corrupt the stream.

Testing through an SDK client alone is insufficient because the client consumes
stdout and may normalize errors. The raw harness tests what another process actually
receives:

```text
server stdout -> one JSON-RPC object per non-empty line
server stderr -> logs, warnings, and diagnostics
```

## Validation Matrix

| Case | Required result |
|---|---|
| `CUST-1234` | `-32602` |
| Arabic-Indic customer digits | `-32602` |
| Amount `0.0` | `-32602` |
| Amount `"50.00"` | `-32602` |
| Nine-character reason | `-32602` |
| 1,001-character reason | `-32602` |
| Extra `is_admin` field | `-32602` |
| Missing arguments | `-32602` |
| Unknown tool name | `-32601` |
| Valid but unknown customer | Tool result with `isError=true` |
| Refund exceeding balance | Tool result with `isError=true` |
| Valid request after invalid request | Normal successful tool result |

## Request ID Preservation

Every invalid-parameter case is sent with JSON-RPC request ID `0`.

The test asserts:

```text
response.id == 0
response.error.code == -32602
response.error.message == "Invalid params"
```

ID `0` is deliberate. Code that checks an ID using truthiness can accidentally drop
it even though zero is a valid JSON-RPC identifier.

## Error-Disclosure Assertions

The serialized validation error data must not contain:

```text
pydantic_core
Traceback
File "
http://
https://
```

This prevents raw exception internals, file locations, and Pydantic documentation
URLs from becoming part of the client-facing error response.

The response may still contain safe field-level details such as the location,
validation type, message, and caller-supplied input.

## Unicode Customer-ID Test

The permanent fixture is the actual Arabic-Indic sequence, verified as:

```text
CUST-\u0661\u0662\u0663\u0664\u0665
```

It returns `-32602` because the contract uses:

```text
^CUST-[0-9]{5}$
```

The test protects against accidentally changing the pattern back to Python `\d`,
which also matches non-ASCII decimal digits.

## Business Errors Remain Tool Results

Two Phase 2 regressions are permanent:

### Unknown customer

`CUST-99999` is structurally valid but absent from the fixture store. The response
must have a normal JSON-RPC `result` containing `isError=true`.

### Refund exceeds balance

A refund of `50.01` for a customer with `50.00` available must also be a tool result
with `isError=true`, not JSON-RPC `-32602`.

These tests preserve the distinction between invalid parameters and valid requests
that fail domain rules.

## Session Recovery

One test sends a refund with amount `"50.00"`, receives `-32602`, and then sends a
valid customer lookup over the same initialized session.

The second request succeeds. This proves the custom handler does not leave the
session unusable after validation failure.

## Commands

### Run all Phase 3 tests

```powershell
.\.venv\Scripts\python.exe -m pytest task1\tests -v
```

### Run the concise suite

```powershell
.\.venv\Scripts\python.exe -m pytest task1\tests -q
```

### Prove the purity test fails on contamination

PowerShell:

```powershell
$env:MCP_SELFTEST = '1'
.\.venv\Scripts\python.exe -m pytest task1\tests\test_stdout_purity.py -q
Remove-Item Env:MCP_SELFTEST
```

The pytest command is expected to fail. The environment variable must be removed
before running the normal suite again.

### Confirm the normal suite after clearing the flag

```powershell
.\.venv\Scripts\python.exe -m pytest task1\tests -q
```

### Audit production source for stdout writers

```powershell
rg -n "print\(|sys\.stdout" `
  task1\server.py task1\models.py task1\store.py
```

Expected result: no matches.

## Actual Validation Results

### Normal suite

```text
..............                                                           [100%]
14 passed in 9.70s
TEST_EXIT=0
```

Result: **PASS**.

### Deliberate contamination self-test

```text
MCP_SELFTEST_STDOUT_CONTAMINATION
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
SELFTEST_EXIT=1
```

Result: **PASS as a test of the test**. Failure is required because the injected
line is not JSON.

### Normal suite after clearing the flag

The complete suite passed again after removing `MCP_SELFTEST`.

Result: **PASS**.

### Source audit

```text
NO_SERVER_STDOUT_WRITERS
```

Result: **PASS**.

### Blank-input startup regression

```text
EXIT=0
STDOUT_BYTES=0
TRACEBACK_PRESENT=False
SELFTEST_ENV=
```

Result: **PASS**. The self-test flag was cleared, startup produced no stdout bytes,
and the process exited cleanly.

### Dependency integrity

```text
No broken requirements found.
```

Result: **PASS**.

### Temporary artifact cleanup

```text
TMP_VALIDATION_EXISTS=False
```

Result: **PASS**.

## Issue Found During Test Review

The initial console display of the Arabic-Indic fixture appeared as mojibake under
PowerShell's legacy encoding. The Python value was explicitly inspected with
`unicode_escape` and confirmed to contain the intended Unicode code points. The
permanent test therefore exercises real Arabic-Indic digits, not merely malformed
text that would be rejected for an unrelated reason.

## Design Decisions

### Raw protocol harness instead of SDK-only tests

The assessment scores JSON-RPC behavior and stdout isolation. Raw frames provide
direct evidence for both and expose ID-preservation bugs that an SDK can hide.

### Self-test uses direct file-descriptor output

The deliberate branch uses file descriptor 1 so it models protocol contamination
without adding a normal `print()` or `sys.stdout` writer to production paths.

### Assert exact codes

Tests assert `-32602` and `-32601`; they do not accept any generic error. Protocol
compliance is part of the external contract.

### Preserve business-error semantics

Hardening the protocol must not turn Phase 2 domain failures into protocol errors.
Dedicated tests prevent that regression.

## Known Limitations

- The raw harness implements only the MCP operations required by these tests.
- Tests are Windows-compatible but have not yet been run on Linux or macOS.
- The custom validation handler still relies on version-sensitive FastMCP internals.
- Phase 3 does not solve refund idempotency or concurrent balance updates.
- The self-test branch must never be enabled in a normal run.

## Completion Gate

- [x] A real server subprocess is driven over raw stdio.
- [x] Every normal stdout line parses as JSON-RPC.
- [x] The purity test fails under deliberate contamination.
- [x] The self-test flag is empty after validation.
- [x] Invalid inputs return exact code `-32602`.
- [x] Request ID `0` is preserved.
- [x] Unknown tools return exact code `-32601`.
- [x] Error data contains no tested internal disclosures.
- [x] Arabic-Indic digits are genuinely tested and rejected.
- [x] Business failures remain error tool results.
- [x] Sessions remain usable after validation errors.
- [x] Phase 2 over-balance behavior remains covered.
- [x] Production source has no `print()` or `sys.stdout` writer.
- [x] The complete normal suite passes.
- [x] Blank-input stdout isolation still passes.
- [x] Dependencies remain consistent.

## Phase Boundary

Phase 3 intentionally does not include:

- the final reviewer-facing `task1/README.md`;
- clean-clone verification;
- final two-command reviewer setup;
- authentication or authorization;
- persistent storage;
- refund idempotency; or
- concurrency-safe balance updates.

Phase 4 may now consolidate the runbook, contracts, design decisions, limitations,
and clean-clone verification into the final reviewer-facing submission.
