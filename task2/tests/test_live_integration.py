import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from typing import Iterator

import httpx
import pytest


ROOT = Path(__file__).resolve().parents[2]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_app(import_path: str, port: int, env: dict[str, str]) -> subprocess.Popen:
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            import_path,
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=ROOT,
        env={**os.environ, **env},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )


def wait_for_health(url: str) -> None:
    deadline = time.monotonic() + 10
    with httpx.Client(trust_env=False) as client:
        while time.monotonic() < deadline:
            try:
                if client.get(url, timeout=0.5).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.05)
    raise AssertionError(f"service did not become healthy: {url}")


def stop_processes(processes: Iterator[subprocess.Popen]) -> None:
    items = list(processes)
    for process in items:
        if process.poll() is None:
            process.terminate()
    for process in items:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


@pytest.mark.asyncio
async def test_real_services_never_forward_denied_calls_and_keep_concurrent_ids(
    tmp_path: Path,
) -> None:
    downstream_port = free_port()
    gateway_port = free_port()
    audit_file = tmp_path / "downstream.jsonl"
    downstream = start_app(
        "task2.downstream.mock_server:app",
        downstream_port,
        {"TASK2_DOWNSTREAM_AUDIT_FILE": str(audit_file)},
    )
    gateway = start_app(
        "task2.gateway.app:app",
        gateway_port,
        {"TASK2_DOWNSTREAM_URL": f"http://127.0.0.1:{downstream_port}"},
    )
    try:
        wait_for_health(f"http://127.0.0.1:{downstream_port}/health")
        wait_for_health(f"http://127.0.0.1:{gateway_port}/health")
        url = f"http://127.0.0.1:{gateway_port}/mcp"

        requests: list[tuple[str, str, str | None]] = []
        for index in range(10):
            requests.append((f"viewer-{index}", "admin_reset_key", "Bearer token-viewer-001"))
            requests.append((f"anonymous-{index}", "admin_reset_key", None))
        for index in range(5):
            requests.append((f"ordinary-{index}", "search_orders", "Bearer token-viewer-001"))
            requests.append((f"admin-{index}", "admin_reset_key", "Bearer token-admin-001"))
            requests.append((f"list-{index}", "", None))

        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            async def send(item: tuple[str, str, str | None]) -> tuple[str, dict]:
                request_id, name, token = item
                headers = {"authorization": token} if token else {}
                payload = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": "tools/list" if request_id.startswith("list-") else "tools/call",
                }
                if name:
                    payload["params"] = {"name": name, "arguments": {}}
                response = await client.post(url, json=payload, headers=headers)
                assert response.status_code == 200
                return request_id, response.json()

            results = await asyncio.gather(*(send(item) for item in requests))

            concurrent = [
                (f"race-{index}", "search_orders" if index % 2 == 0 else "admin_reset_key")
                for index in range(100)
            ]

            async def race(item: tuple[str, str]) -> tuple[str, dict]:
                request_id, name = item
                response = await client.post(
                    url,
                    json={
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "method": "tools/call",
                        "params": {"name": name, "arguments": {}},
                    },
                    headers={"authorization": "Bearer token-viewer-001"},
                )
                return request_id, response.json()

            race_results = await asyncio.gather(*(race(item) for item in concurrent))

        assert all(expected == body["id"] for expected, body in results + race_results)
        denied = [body for _, body in results + race_results if body.get("error", {}).get("code") == -32001]
        assert len(denied) == 70

        audit_rows = [json.loads(line) for line in audit_file.read_text(encoding="utf-8").splitlines()]
        assert len(audit_rows) == 65
        assert not any(
            str(row["id"]).startswith(("viewer-", "anonymous-")) for row in audit_rows
        )
        assert not any(
            str(row["id"]).startswith("race-") and int(str(row["id"]).split("-")[1]) % 2
            for row in audit_rows
        )
    finally:
        stop_processes(iter((gateway, downstream)))


def test_live_timeout_disconnect_header_filter_and_response_limit() -> None:
    downstream_port = free_port()
    gateway_port = free_port()
    downstream = start_app("task2.tests.probe_server:app", downstream_port, {})
    gateway = start_app(
        "task2.gateway.app:app",
        gateway_port,
        {
            "TASK2_DOWNSTREAM_URL": f"http://127.0.0.1:{downstream_port}",
            "TASK2_UPSTREAM_READ_TIMEOUT": "0.25",
            "TASK2_MAX_RESPONSE_BYTES": "1024",
        },
    )
    try:
        wait_for_health(f"http://127.0.0.1:{downstream_port}/health")
        wait_for_health(f"http://127.0.0.1:{gateway_port}/health")
        gateway_url = f"http://127.0.0.1:{gateway_port}/mcp"
        state_url = f"http://127.0.0.1:{downstream_port}/state"
        admin = {"authorization": "Bearer token-admin-001"}

        with httpx.Client(timeout=5, trust_env=False) as client:
            started = time.monotonic()
            timeout_response = client.post(
                gateway_url,
                json={
                    "jsonrpc": "2.0",
                    "id": "hang",
                    "method": "tools/call",
                    "params": {"name": "admin_hang", "arguments": {}},
                },
                headers=admin,
            )
            elapsed = time.monotonic() - started
            assert timeout_response.json()["error"]["code"] == -32603
            assert elapsed < 2

            deadline = time.monotonic() + 2
            state = client.get(state_url).json()
            while state["hangs"]["abandoned"] != 1 and time.monotonic() < deadline:
                time.sleep(0.05)
                state = client.get(state_url).json()
            assert state["hangs"] == {
                "started": 1,
                "active": 0,
                "abandoned": 1,
                "completed": 0,
            }

            header_response = client.post(
                gateway_url,
                json={
                    "jsonrpc": "2.0",
                    "id": "headers",
                    "method": "tools/call",
                    "params": {"name": "search_orders", "arguments": {}},
                },
                headers={
                    "authorization": "Bearer token-viewer-001",
                    "x-forwarded-for": "203.0.113.9",
                    "x-internal-auth": "spoofed",
                },
            )
            assert header_response.status_code == 200
            headers = dict(client.get(state_url).json()["calls"][-1]["headers"])
            assert "authorization" not in headers
            assert "x-forwarded-for" not in headers
            assert "x-internal-auth" not in headers
            assert headers["host"] == f"127.0.0.1:{downstream_port}"

            large_response = client.post(
                gateway_url,
                json={
                    "jsonrpc": "2.0",
                    "id": "large",
                    "method": "tools/call",
                    "params": {"name": "admin_large", "arguments": {}},
                },
                headers=admin,
            )
            assert large_response.json()["error"]["code"] == -32603
            assert len(large_response.content) < 1_024
    finally:
        stop_processes(iter((gateway, downstream)))
