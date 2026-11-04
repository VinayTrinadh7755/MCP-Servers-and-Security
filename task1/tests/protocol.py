"""Small raw-stdio MCP client used by protocol integration tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SERVER_PATH = PROJECT_ROOT / "task1" / "server.py"


class RawMCPClient:
    """Drive the server as newline-delimited JSON-RPC without SDK normalization."""

    def __init__(self) -> None:
        self.process: subprocess.Popen[str] | None = None
        self.stdout_lines: list[str] = []
        self.stderr = ""
        self._next_id = 1

    def __enter__(self) -> RawMCPClient:
        self.process = subprocess.Popen(
            [sys.executable, str(SERVER_PATH)],
            cwd=PROJECT_ROOT,
            env=os.environ.copy(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        response = self.request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "task1-tests", "version": "1.0"},
            },
        )
        assert "result" in response
        self.notify("notifications/initialized")
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        assert self.process is not None
        if self.process.stdin is not None and not self.process.stdin.closed:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)

        if self.process.stdout is not None:
            self.stdout_lines.extend(
                line.rstrip("\r\n") for line in self.process.stdout.readlines()
            )
        if self.process.stderr is not None:
            self.stderr = self.process.stderr.read()

    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        request_id: int | None = None,
    ) -> dict[str, Any]:
        if request_id is None:
            request_id = self._next_id
            self._next_id += 1
        message: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params is not None:
            message["params"] = params
        self._write(message)
        return self._read()

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        message: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        self._write(message)

    def _write(self, message: dict[str, Any]) -> None:
        assert self.process is not None and self.process.stdin is not None
        self.process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
        self.process.stdin.flush()

    def _read(self) -> dict[str, Any]:
        assert self.process is not None and self.process.stdout is not None
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError("Server stdout closed before a response arrived")
        line = line.rstrip("\r\n")
        self.stdout_lines.append(line)
        return json.loads(line)
