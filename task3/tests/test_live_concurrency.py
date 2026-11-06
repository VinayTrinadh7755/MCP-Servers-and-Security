from __future__ import annotations

import asyncio
import json
import os
import socket
import string
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator

import httpx
import pytest


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_ready(url: str, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if httpx.get(url, timeout=0.5, trust_env=False).status_code == 200:
                return
        except httpx.HTTPError:
            time.sleep(0.05)
    raise AssertionError(f"service did not become ready: {url}")


@pytest.fixture
def live_services() -> Iterator[tuple[str, subprocess.Popen[str], object]]:
    provider_port = free_port()
    gateway_port = free_port()
    provider = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "task3.provider.mock_provider:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(provider_port),
            "--log-level",
            "warning",
        ],
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    env = os.environ.copy()
    env["TASK3_PROVIDER_URL"] = (
        f"http://127.0.0.1:{provider_port}/v1/chat/completions"
    )
    gateway_log = tempfile.TemporaryFile(mode="w+", encoding="utf-8")
    gateway = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "task3.gateway.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(gateway_port),
            "--log-level",
            "info",
            "--no-access-log",
        ],
        env=env,
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=gateway_log,
    )
    try:
        wait_ready(f"http://127.0.0.1:{gateway_port}/health")
        yield f"http://127.0.0.1:{gateway_port}/v1/chat/completions", gateway, gateway_log
    finally:
        for process in (gateway, provider):
            if process.poll() is None:
                process.terminate()
        for process in (gateway, provider):
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        gateway_log.close()


def assembled_text(body: str) -> str:
    output: list[str] = []
    for line in body.splitlines():
        if line.startswith("data: {"):
            payload = json.loads(line[6:])
            choices = payload.get("choices", [])
            if choices:
                output.append(choices[0].get("delta", {}).get("content", ""))
    return "".join(output)


def marker(index: int) -> str:
    return "REQ" + string.ascii_uppercase[index // 26] + string.ascii_uppercase[index % 26]


async def concurrent_batch(url: str, kind: str) -> tuple[int, float]:
    cards = [str(4_000_000_000_000_000 + index) for index in range(50)]
    emails = [
        f"user{string.ascii_lowercase[index // 26]}{string.ascii_lowercase[index % 26]}@example.com"
        for index in range(50)
    ]
    markers = [marker(index) for index in range(50)]
    async with httpx.AsyncClient(
        timeout=30.0,
        trust_env=False,
        limits=httpx.Limits(max_connections=100),
    ) as client:
        async def one(index: int) -> tuple[int, int, str, str]:
            text = f"{markers[index]} {cards[index]}"
            if kind == "mixed":
                text += f" {emails[index]}"
            response = await client.post(
                url,
                json={
                    "text": text,
                    "stream": True,
                    "chunk_size": 3 if kind == "mixed" else 1,
                    "delay_ms": 0,
                },
            )
            return index, response.status_code, assembled_text(response.text), response.text

        started = time.perf_counter()
        rows = await asyncio.gather(*(one(index) for index in range(50)))
        elapsed = time.perf_counter() - started

    failures = 0
    for index, status, output, raw_body in rows:
        expected = f"{markers[index]} [REDACTED]"
        if kind == "mixed":
            expected += " [REDACTED]"
        foreign_markers = [value for offset, value in enumerate(markers) if offset != index]
        if (
            status != 200
            or output != expected
            or any(value in output for value in cards + emails)
            or any(value in output for value in foreign_markers)
            or not raw_body.endswith("data: [DONE]\n\n")
        ):
            failures += 1
    return failures, elapsed


def test_fifty_concurrent_mixed_and_one_character_card_streams_are_isolated(
    live_services: tuple[str, subprocess.Popen[str], object],
) -> None:
    url, gateway, gateway_log = live_services
    mixed_failures, mixed_elapsed = asyncio.run(concurrent_batch(url, "mixed"))
    card_failures, card_elapsed = asyncio.run(concurrent_batch(url, "card-split"))
    assert mixed_failures == 0
    assert card_failures == 0
    assert mixed_elapsed < 15
    assert card_elapsed < 15

    # Counters are logged once from each request-scoped guardrail. A global
    # counter would produce increasing values rather than these stable groups.
    gateway.terminate()
    gateway.wait(timeout=10)
    gateway_log.seek(0)  # type: ignore[attr-defined]
    stderr = gateway_log.read()  # type: ignore[attr-defined]
    counter_lines = [line for line in stderr.splitlines() if "stream redactions=" in line]
    assert len(counter_lines) == 100
    assert sum("'card': 1, 'email': 1" in line for line in counter_lines) == 50
    assert sum("'card': 1, 'email': 0" in line for line in counter_lines) == 50
