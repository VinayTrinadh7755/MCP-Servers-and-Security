#!/usr/bin/env bash
set -euo pipefail

gateway_port="${TASK3_GATEWAY_PORT:-8100}"
provider_port="${TASK3_PROVIDER_PORT:-8101}"
python_bin="${PYTHON:-python}"
export TASK3_PROVIDER_URL="http://127.0.0.1:${provider_port}/v1/chat/completions"

"${python_bin}" -m uvicorn task3.provider.mock_provider:app --host 127.0.0.1 --port "${provider_port}" &
provider_pid=$!
"${python_bin}" -m uvicorn task3.gateway.app:app --host 127.0.0.1 --port "${gateway_port}" &
gateway_pid=$!

cleanup() {
  kill "${gateway_pid}" "${provider_pid}" 2>/dev/null || true
  wait "${gateway_pid}" "${provider_pid}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
echo "Gateway: http://127.0.0.1:${gateway_port}"
echo "Provider: http://127.0.0.1:${provider_port}"
wait -n "${gateway_pid}" "${provider_pid}"
