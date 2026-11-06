"""Consume Task 3 SSE frames and print their arrival time."""

from __future__ import annotations

import argparse
import json
import time

import httpx


EXPECTED_CLEAN_FIXTURES = {
    "plain": "Streaming proves that each delta reaches the client progressively.",
    "single": "one frame",
    "empty": "",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", default="plain")
    parser.add_argument("--url", default="http://127.0.0.1:8100/v1/chat/completions")
    parser.add_argument("--chunk-size", type=int)
    parser.add_argument("--delay-ms", type=int)
    parser.add_argument("--assert-identical", action="store_true")
    args = parser.parse_args()

    payload: dict[str, object] = {"fixture": args.fixture, "stream": True}
    if args.chunk_size is not None:
        payload["chunk_size"] = args.chunk_size
    if args.delay_ms is not None:
        payload["delay_ms"] = args.delay_ms

    started = time.perf_counter()
    assembled: list[str] = []
    saw_done = False
    with httpx.stream("POST", args.url, json=payload, timeout=30.0, trust_env=False) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if line:
                elapsed_ms = (time.perf_counter() - started) * 1000
                print(f"{elapsed_ms:9.2f} ms  {line}", flush=True)
                if line == "data: [DONE]":
                    saw_done = True
                elif line.startswith("data: "):
                    event = json.loads(line[6:])
                    choices = event.get("choices", [])
                    if choices:
                        assembled.append(choices[0].get("delta", {}).get("content", ""))
    if not saw_done:
        raise RuntimeError("stream ended without [DONE]")
    if args.assert_identical:
        if args.fixture not in EXPECTED_CLEAN_FIXTURES:
            raise ValueError("--assert-identical supports plain, single, and empty fixtures")
        if "".join(assembled) != EXPECTED_CLEAN_FIXTURES[args.fixture]:
            raise AssertionError("assembled gateway output differs from provider fixture")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
