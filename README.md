# MCP Servers

A Python project for building Model Context Protocol (MCP) servers.

## Assessment Tasks

- [Task 1 — Customer Operations MCP Server](task1/README.md)
- [Task 2 — MCP Security Gateway](task2/README.md)

- [Task 3 — Streaming PII Guardrail](task3/README.md)

## Task 1 Quick Start

```powershell
py -3.11-64 -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest task1\tests -q; .\.venv\Scripts\python.exe task1\scripts\drive.py
```

See `task1/README.md` for contracts, design decisions, validation commands, and
trade-offs.

## Task 2 Quick Start

```powershell
py -3.11-64 -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest task2\tests -q
```

See `task2/README.md` for the policy matrix, threat model, live-service commands,
design decisions, and production trade-offs.

## Task 3 Quick Start

```powershell
.\task3\scripts\run_both.ps1
.\.venv\Scripts\python.exe task3\scripts\consume.py --fixture plain
```

See `task3/README.md` for streaming fixtures, configuration, and tests.
