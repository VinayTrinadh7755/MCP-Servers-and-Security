# Task 1 — Phase 0: Foundation

## Status

Phase 0 is complete.

This phase establishes a minimal Model Context Protocol (MCP) server that:

- uses the official Python MCP SDK;
- runs over the `stdio` transport;
- exposes zero tools;
- reserves stdout for MCP protocol messages;
- sends application and SDK logs to stderr;
- can be launched and inspected by an SDK-based client; and
- installs reproducibly from pinned direct dependencies.

No Task 1 schemas, tools, customer records, refund behavior, or validation rules were implemented in this phase. Those belong to later phases.

## Objective

Create the smallest runnable MCP server and prove that the project environment, stdio transport, SDK client connection, and process shutdown work before adding tool contracts or business logic.

## Files Created

### `task1/__init__.py`

Marks `task1` as a Python package.

### `task1/server.py`

Contains the minimal MCP server.

Its responsibilities are deliberately limited to:

1. configuring the root Python logger to use `sys.stderr`;
2. filtering whitespace-only stdio frames before JSON-RPC parsing;
3. delegating transport framing and JSON-RPC parsing to the official SDK;
4. creating a `FastMCP` instance named `customer-operations`; and
5. starting the server with the stdio transport when executed directly.

The server currently registers no tools. An empty tool list is the expected Phase 0 contract.

### `task1/scripts/drive.py`

Contains the Phase 0 verification client. It uses the official MCP SDK instead of manually writing JSON-RPC frames.

The driver:

1. launches `task1/server.py` with the same Python interpreter running the driver;
2. opens an MCP stdio connection;
3. creates and initializes an MCP `ClientSession`;
4. requests `tools/list` through `session.list_tools()`;
5. prints the returned tool names; and
6. closes the session and server process through async context managers.

The expected output is:

```text
[]
```

### `requirements.txt`

Pins the direct Phase 0 dependencies:

```text
mcp==1.27.2
pydantic==2.12.5
pytest==9.0.3
pytest-asyncio==1.3.0
```

`pytest` and `pytest-asyncio` are installed now so later phases can add protocol and subprocess tests without changing the basic environment unexpectedly.

### `.gitignore`

Excludes local and generated Python artifacts:

```text
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
```

## Design Decisions

### Use the official MCP SDK on both sides

The server uses `FastMCP`, and the verification driver uses `stdio_client` and `ClientSession` from the official SDK. This proves compatibility with the SDK's real initialization and request flow instead of testing a hand-written approximation of MCP JSON-RPC.

### Use stdio from the beginning

Task 1 explicitly requires stdio. Establishing this transport before defining tools isolates setup and lifecycle failures from later schema or business-logic failures.

### Keep logs on stderr

For an MCP stdio server, stdout is a protocol channel, not a general console. A normal `print()` or stdout log can corrupt the JSON-RPC stream.

`configure_stderr_logging()` therefore:

1. obtains the root logger;
2. removes existing handlers;
3. installs a `logging.StreamHandler(sys.stderr)`; and
4. applies a compact timestamp, level, logger name, and message format.

Removing existing handlers matters because imported libraries may configure the root logger before application configuration runs. Calling `logging.basicConfig()` alone may then have no effect.

Mechanical stdout-purity tests are intentionally deferred to Phase 3. Phase 0 establishes the correct logging path and proves a real SDK round trip.

Phase 0 also includes a direct stream-splitting probe. That probe confirms that
startup and whitespace-only input produce zero stdout bytes. Phase 3 will add the
permanent automated subprocess test that exercises complete valid and invalid MCP
sessions.

### Ignore whitespace-only stdio frames

The original SDK transport treated a blank input line as malformed JSON and sent
an error notification to stdout. The validation command uses `"" | server.py`,
which sends a newline before EOF rather than EOF alone. Consequently, the first
validation run produced a valid MCP error notification and
`STDOUT_BYTES=302` under PowerShell 5.1's redirected UTF-16 output.

`WhitespaceTolerantFastMCP` now overrides only the stdio startup path. Its async
input iterator discards lines for which `line.strip()` is empty, then passes every
nonblank line to the official SDK's `stdio_server`. The SDK still owns JSON-RPC
model validation, output serialization, framing, initialization, and request
dispatch.

This is transport hardening, not Phase 1 behavior. No tools, schemas, customer
records, or refund logic were added.

### Launch the server with the active interpreter

The driver uses `sys.executable` rather than a hard-coded `python` command. This ensures the child server uses the same virtual environment and installed SDK version as the client.

### Pin direct dependencies

Exact direct dependency versions make the assessment reproducible and prevent an SDK upgrade from changing behavior while the remaining phases are being built.

The file does not freeze every transitive package. This keeps the dependency declaration readable while still locking the libraries the project imports and tests directly. A fully locked transitive dependency file can be added later if the submission requires byte-for-byte environment reproduction.

## Environment Setup

The validated environment uses Python 3.11.9 x64 on Windows.

From the repository root:

```powershell
py -3.11-64 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

All project commands use `.\.venv\Scripts\python.exe` explicitly. A bare `python`
must not be used on this machine because it resolves to the ARM64 interpreter.

## How to Run the Phase 0 Driver

From the repository root:

```powershell
.\.venv\Scripts\python.exe task1\scripts\drive.py
```

Expected functional output:

```text
[]
```

The empty list confirms that:

- the server process started;
- the client connected over stdio;
- MCP session initialization completed;
- `tools/list` reached the server;
- the server returned its current zero-tool contract; and
- the client and server shut down normally.

The MCP SDK may emit an `IncompleteFieldDefinitionWarning` from `pydantic_settings` on stderr. It does not appear on the MCP protocol stream and did not prevent initialization, listing tools, or clean shutdown. It is an upstream compatibility warning in the pinned dependency set, not an application error.

## Dependency Verification

Display the installed MCP and Pydantic versions:

```powershell
.\.venv\Scripts\python.exe -c "import importlib.metadata, pydantic; print(importlib.metadata.version('mcp'), pydantic.VERSION)"
```

Verified output:

```text
1.27.2 2.12.5
```

Check dependency consistency:

```powershell
.\.venv\Scripts\python.exe -m pip check
```

Verified output:

```text
No broken requirements found.
```

### Why `cryptography` is installed

The dependency tree was inspected with `pipdeptree`. MCP 1.27.2 directly declares:

```text
pyjwt[crypto]>=2.10.1
```

The resulting path is:

```text
mcp==1.27.2
└── PyJWT[crypto]>=2.10.1
    └── cryptography>=3.4.0
```

This is not caused by an optional extra selected in this project's
`requirements.txt`. It is part of MCP 1.27.2's own installed metadata, so a normal
installation of this pinned MCP release cannot omit `cryptography` while still
letting pip satisfy the declared dependency set.

## Validation Results

### Happy path

Command:

```powershell
.\.venv\Scripts\python.exe task1\scripts\drive.py
```

Observed result:

```text
[]
```

Result: passed.

### Clean shutdown

The driver execution was timed from process start through complete shutdown.

Observed result:

```text
EXIT=0 ELAPSED_MS=1533
```

Result: passed. The client and child server exited normally without hanging.

### Installed versions

Observed result:

```text
1.27.2 2.12.5
```

Result: passed.

### Dependency integrity

Observed result:

```text
No broken requirements found.
```

Result: passed.

### Clean-environment installation

A disposable x64 Python 3.11 virtual environment was created outside the repository. `requirements.txt` was installed into it, package versions were checked, and `pip check` was run.

Observed result:

```text
1.27.2 2.12.5
No broken requirements found.
```

Result: passed. The disposable environment was removed after verification.

## Final Six-Check Validation Pass

### Check 1: server stdout on startup

The server was given the checklist's blank-line-then-EOF input with stdout and
stderr redirected separately.

```text
EXIT=0
STDOUT_BYTES=0
```

Result: **PASS**. The process exited cleanly and wrote no startup banner or other
bytes to stdout. The `IncompleteFieldDefinitionWarning` appeared only on stderr.

### Check 2: no server-path stdout writers

The server and package initializer were searched for `print(`, `sys.stdout`, and
`basicConfig`.

```text
NO_MATCHES
```

Result: **PASS**. The code clears existing root handlers before attaching its own
`StreamHandler(sys.stderr)`.

### Check 3: empirical logging destination

A warning was emitted through a probe logger after applying the server's logging
configuration.

```text
EXIT=0
OUT_BYTES=0
2026-11-02 20:05:23,150 WARNING probe PROBE_LINE
```

Result: **PASS**. The output capture was empty, and `PROBE_LINE` was present in the
stderr capture.

### Check 4: abrupt client termination

The SDK driver was started, force-stopped after 400 milliseconds, and the process
table was inspected three seconds later for a Python process whose command line
contained `server.py`.

```text
<no rows returned>
```

Result: **PASS**. The abrupt client death left no orphaned MCP server process.

### Check 5: interpreter architecture

```text
AMD64 64bit 3.11.9 (tags/v3.11.9:de54cf5, Apr  2 2024, 10:12:12) [MSC v.1938 64 bit (AMD64)]
```

Result: **PASS**. The project uses x64 Python under emulation on the Windows ARM64
host, which allows pip to use the available prebuilt dependency wheels.

### Check 6: `cryptography` dependency source

`pipdeptree --packages mcp` showed:

```text
mcp==1.27.2
  - PyJWT [required: >=2.10.1, installed: 2.15.1]
    - cryptography [required: >=3.4.0, installed: 50.0.2, extra: crypto]
```

The MCP package metadata independently reported:

```text
pyjwt[crypto]>=2.10.1
```

Result: **PASS**. The source of `cryptography` is understood and documented. It is
unavoidable when installing MCP 1.27.2 with its declared dependencies.

The final integrity check remained:

```text
No broken requirements found.
```

## Issue Encountered: Windows ARM64 Dependency Build

The machine's default `python` command points to Python 3.11 ARM64. Installing the MCP dependency tree with that interpreter attempted to build `cryptography` from source because a compatible wheel was not available. The build failed when the required ARM64 Rust compiler component was unavailable:

```text
the 'rustc.exe' binary ... is not applicable to the
'stable-aarch64-pc-windows-msvc' toolchain
```

The project virtual environment was replaced with one created by the already-installed Python 3.11 x64 interpreter. That environment downloaded compatible prebuilt wheels, and installation completed successfully.

This was an environment compatibility issue, not an MCP server defect. No application source was deleted or rolled back. Only the newly created, incompatible `.venv` directory was replaced.

## Phase 0 Completion Gate

Phase 0 is complete because all of the following are true:

- [x] A pinned Python environment can be installed from `requirements.txt`.
- [x] The official MCP SDK imports successfully.
- [x] The FastMCP server starts with stdio transport.
- [x] An official SDK client initializes a session successfully.
- [x] `tools/list` returns exactly zero tools.
- [x] The driver exits with status code 0.
- [x] The server does not remain hanging after the client session closes.
- [x] Application logging is explicitly configured for stderr.
- [x] The exact startup probe produces `STDOUT_BYTES=0`.
- [x] The server path contains no `print(`, `sys.stdout`, or `basicConfig` writer.
- [x] An empirical log probe writes only to stderr.
- [x] Abrupt client termination leaves no orphaned server process.
- [x] The runtime architecture is recorded as AMD64/x64 Python 3.11.9.
- [x] The `mcp -> PyJWT[crypto] -> cryptography` dependency path is documented.
- [x] Installed MCP and Pydantic versions match the direct pins.
- [x] `pip check` reports no broken requirements.
- [x] Installation succeeds in a fresh disposable virtual environment.

## Phase Boundary

Phase 0 intentionally does not include:

- `get_customer_record`;
- `trigger_refund`;
- Pydantic input models;
- customer ID format validation;
- amount or reason validation;
- fixture customer data;
- refund business logic;
- JSON-RPC validation-error assertions; or
- automated stdout-purity tests.

The next phase may begin by defining and registering the two strict tool schemas with stub implementations. It should not add customer lookup or refund business behavior until the schema contract has been inspected and validated.
