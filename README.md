# MCP Servers

A four-part Python gateway assessment. All tasks share one pinned dependency file
and one virtual environment.

## Assessment Tasks

- [Task 1 - Customer Operations MCP Server](task1/README.md): official MCP SDK,
  strict tool schemas, JSON-RPC errors, and pure stdio transport.
- [Task 2 - MCP Security Gateway](task2/README.md): authenticated JSON-RPC proxy,
  method-level authorization, and transparent downstream forwarding.
- [Task 3 - Streaming PII Guardrail](task3/README.md): bounded-state SSE parsing
  and cross-chunk email, SSN, and card redaction.
- [Task 4 - Token Rate Limiter and Fallback Router](task4/README.md): atomic
  SQLite token admission, reconciliation, bounded failover, and sanitized errors.

## What We Built Across All Phases

Every task followed the same five-stage delivery sequence:

| Phase | Purpose | Submission outcome |
|---|---|---|
| 0 - Foundation | Pinned environment, runnable skeleton, deterministic local fixtures | Every service starts without paid credentials |
| 1 - Structure | Protocol contracts, schemas, routes, interfaces and transports | Inputs and outputs are explicit before business logic |
| 2 - Load-bearing logic | The behavior directly scored by the assessment | MCP tools, authorization, PII redaction and token routing work end to end |
| 3 - Hardening | Malformed input, bypasses, concurrency, cancellation and failure paths | Security and race-condition claims have adversarial tests |
| 4 - Finish | Clean-clone tests, launchers, documentation, benchmarks and trade-offs | One reproducible package for Windows x64 and Ubuntu ARM64 |

Task 1 establishes the protocol baseline with the official MCP SDK and strict
stdio discipline. Task 2 places an authenticated authorization gateway in front
of a downstream MCP service. Task 3 applies bounded-state security controls to an
LLM token stream without collecting the complete response. Task 4 adds atomic
per-tenant token accounting and bounded provider fallback. Together they form a
progression from tool contract, to gateway policy, to streaming data protection,
to resilient multi-provider operation.

## Final Validation Snapshot

| Task | Focused result |
|---|---:|
| Task 1 | 14 passed |
| Task 2 | 54 passed |
| Task 3 | 101 passed |
| Task 4 | 32 passed |

The same counts passed from fresh clones on Windows x64 and Ubuntu ARM64. The
repository uses one `requirements.txt`, one virtual environment, and one root-level
setup path for all four tasks. Each task directory now has exactly one Markdown
document—its `README.md`—containing its phase record, operation guide, validation,
decisions and limitations.

## Shared Setup

From the repository root, create one environment for all four tasks:

```powershell
py -3.11-64 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Linux and macOS:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

## Task 1 Quick Start

```powershell
.\.venv\Scripts\python.exe -m pytest task1\tests -q; .\.venv\Scripts\python.exe task1\scripts\drive.py
```

See `task1/README.md` for contracts, design decisions, validation commands, and
trade-offs.

## Task 2 Quick Start

```powershell
.\.venv\Scripts\python.exe -m pytest task2\tests -q
```

See `task2/README.md` for the policy matrix, threat model, live-service commands,
design decisions, and production trade-offs.

## Task 3 Quick Start

```powershell
.\.venv\Scripts\python.exe -m pytest task3\tests -q
.\.venv\Scripts\python.exe task3\scripts\benchmark.py
```

See `task3/README.md` for streaming fixtures, configuration, and tests.

## Task 4 Quick Start

```powershell
.\.venv\Scripts\python.exe -m pytest task4\tests -q
powershell.exe -ExecutionPolicy Bypass -File .\task4\scripts\run_both.ps1
```

See `task4/README.md` for the atomic reservation algorithm, failover table,
configuration, error contract, validation commands, and production limits.
