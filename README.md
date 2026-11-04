# MCP Servers

A Python project for building Model Context Protocol (MCP) servers.

## Assessment Tasks

- [Task 1 — Customer Operations MCP Server](task1/README.md)

## Task 1 Quick Start

```powershell
py -3.11-64 -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest task1\tests -q; .\.venv\Scripts\python.exe task1\scripts\drive.py
```

See `task1/README.md` for contracts, design decisions, validation commands, and
trade-offs.
