#!/usr/bin/env bash
set -euo pipefail

gateway_port="${TASK4_GATEWAY_PORT:-8200}"
provider_port="${TASK4_PROVIDER_PORT:-8201}"
python_bin="${PYTHON:-python}"
export TASK4_PRIMARY_URL="http://127.0.0.1:${provider_port}/primary/v1/completions"
export TASK4_SECONDARY_URL="http://127.0.0.1:${provider_port}/secondary/v1/completions"

"${python_bin}" -m uvicorn task4.providers.mock_provider:app --host 127.0.0.1 --port "${provider_port}" &
provider_pid=$!
"${python_bin}" -m uvicorn task4.app:app --host 127.0.0.1 --port "${gateway_port}" &
gateway_pid=$!

cleanup() {
  kill "${gateway_pid}" "${provider_pid}" 2>/dev/null || true
  wait "${gateway_pid}" "${provider_pid}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
echo "Gateway: http://127.0.0.1:${gateway_port}"
echo "Providers: http://127.0.0.1:${provider_port}"
wait -n "${gateway_pid}" "${provider_pid}"
