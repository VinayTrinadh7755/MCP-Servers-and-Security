#!/usr/bin/env bash
set -euo pipefail

gateway_port="${GATEWAY_PORT:-8000}"
downstream_port="${DOWNSTREAM_PORT:-8001}"

python -m uvicorn task2.downstream.mock_server:app --host 127.0.0.1 --port "$downstream_port" &
downstream_pid=$!
python -m uvicorn task2.gateway.app:app --host 127.0.0.1 --port "$gateway_port" &
gateway_pid=$!

cleanup() {
  kill "$gateway_pid" "$downstream_pid" 2>/dev/null || true
  wait "$gateway_pid" "$downstream_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

wait -n "$gateway_pid" "$downstream_pid"
