# Task 2 Complete Implementation Documentation

## 1. Completion status

Task 2 is complete and validated. The repository contains a lightweight HTTP/JSON-RPC MCP security gateway, a mock downstream MCP service, a fail-closed authorization policy, adversarial bypass protections, automated tests, and reviewer run instructions.

Final verified state:

- Task 2 tests: **54 passed**.
- Task 1 regression tests: **14 passed**.
- Windows x64 clean-clone validation: passed.
- Ubuntu ARM64 clean-clone validation: passed.
- Dependency integrity with `pip check`: passed.
- Git working tree at completion: clean.
- Tracked virtual environments, caches, databases, bytecode, and package metadata: none.

## 2. Assessment requirement

The task required an HTTP/JSON-RPC reverse proxy between an AI agent and a downstream MCP server. The gateway had to:

1. Read an incoming `Authorization: Bearer <token>` header and resolve a user role.
2. Transparently forward `tools/list`.
3. Inspect `params.name` for `tools/call` requests.
4. Require the `admin` role when a tool name starts with `admin_`.
5. Return JSON-RPC error `-32001: Unauthorized Tool Call` without contacting the downstream when authorization fails.
6. Parse JSON-RPC correctly, forward HTTP requests and responses, and handle failures cleanly.

The central security invariant is:

> A denied request must be rejected before any downstream request or privileged side effect can occur.

## 3. Delivered architecture

```text
MCP client
    |
    | HTTP POST /mcp
    | JSON-RPC request + optional Bearer token
    v
Task 2 gateway :8000
    |
    |-- bounded body read
    |-- strict JSON parsing and duplicate-key rejection
    |-- method and tool-name validation
    |-- token-to-role resolution
    |-- authorization decision
    |
    | DENY ----------------> JSON-RPC error returned directly
    |                         downstream is not contacted
    |
    | ALLOW
    v
Mock MCP downstream :8001
    |
    |-- tools/list returns four tools
    |-- tools/call returns an execution result
    |-- every received request is logged
    v
Gateway returns downstream JSON-RPC response to client
```

The gateway and downstream are separate FastAPI applications. The gateway uses one shared asynchronous HTTPX client, created at application startup and closed at shutdown. The shared client provides connection pooling and avoids creating a new TCP client for every request.

## 4. Repository layout

```text
task2/
|-- README.md
|-- TASK2_COMPLETE_DOCUMENTATION.md
|-- __init__.py
|-- downstream/
|   |-- __init__.py
|   `-- mock_server.py
|-- gateway/
|   |-- __init__.py
|   |-- app.py
|   |-- auth.py
|   |-- policy.py
|   `-- upstream.py
|-- scripts/
|   |-- run_both.ps1
|   `-- run_both.sh
`-- tests/
    |-- __init__.py
    |-- probe_server.py
    |-- test_auth_policy.py
    |-- test_bypass.py
    |-- test_live_integration.py
    |-- test_logging.py
    |-- test_proxy.py
    `-- test_upstream.py
```

### File responsibilities

| File | Responsibility |
|---|---|
| `downstream/mock_server.py` | Mock JSON-RPC MCP service, four tool definitions, tool execution echo, and request logging. |
| `gateway/app.py` | HTTP boundary, bounded body reading, JSON parsing, authorization orchestration, error responses, and forwarding. |
| `gateway/auth.py` | Exact Bearer-header parsing and static demo token-to-identity mapping. |
| `gateway/policy.py` | Pure allow/deny decision logic for MCP methods and tool names. |
| `gateway/upstream.py` | Shared HTTPX client, timeout configuration, forwarding, response validation, and downstream failure abstraction. |
| `scripts/run_both.sh` | Starts the gateway and downstream together and cleans up both processes on exit. |
| `scripts/run_both.ps1` | Native Windows launcher with configurable ports and child-process cleanup. |
| `tests/test_auth_policy.py` | Unit tests for token resolution and policy decisions. |
| `tests/test_proxy.py` | Gateway request-flow, forwarding, ID preservation, blocking, and sanitization tests. |
| `tests/test_bypass.py` | Hostile payload, ambiguity, smuggling, batch, and size-limit tests. |
| `tests/test_live_integration.py` | Real Uvicorn-process non-forwarding, concurrency, timeout disconnect, header, and response-limit tests. |
| `tests/test_logging.py` | Correlation-ID, diagnostic-detail, and token-exclusion tests. |
| `tests/test_upstream.py` | Downstream HTTP failure and malformed-response tests. |
| `README.md` | Concise reviewer instructions, policy table, threat model, decisions, and trade-offs. |

## 5. Dependency changes

The following pinned dependencies were added to both `requirements.txt` and `pyproject.toml`:

```text
fastapi==0.162.0
uvicorn==0.54.0
httpx==0.28.1
```

The package discovery configuration was expanded from `task1*` to `task1*` and `task2*`. Task 1 dependencies and behavior were preserved.

## 6. Phase-by-phase implementation

## Phase 0: Foundation

### Objective

Establish two independently runnable HTTP services: a mock MCP downstream and an empty gateway shell.

### Work completed

1. Added and pinned FastAPI, Uvicorn, and HTTPX.
2. Created the `task2` Python package and its downstream, gateway, scripts, and tests structure.
3. Implemented downstream `GET /health` and gateway `GET /health` endpoints.
4. Implemented downstream `POST /mcp` with JSON-RPC handling.
5. Added four downstream tools:
   - `get_customer_record`
   - `search_orders`
   - `admin_reset_key`
   - `admin_delete_tenant`
6. Implemented downstream `tools/list` and `tools/call` behavior.
7. Added downstream JSON-RPC errors:
   - `-32700` for malformed JSON.
   - `-32600` for an invalid request structure.
   - `-32601` for an unknown method.
   - `-32602` for invalid `tools/call` parameters.
8. Added structured downstream request logs.
9. Added `run_both.sh`, including signal cleanup and configurable ports.

### Phase 0 validation

- Both health endpoints returned HTTP 200.
- `tools/list` returned exactly four tools.
- An unknown method returned `-32601`.
- Malformed JSON returned `-32700` without a stack trace in the response.
- Downstream requests appeared in the service log.
- All 14 Task 1 tests still passed.

### Phase 0 commit

```text
3fac304 feat: scaffold Task 2 gateway services
```

## Phase 1: Transparent proxy structure

### Objective

Forward valid JSON-RPC requests through the gateway without authorization logic, while preserving IDs and sanitizing downstream failures.

### Work completed

1. Added gateway `POST /mcp`.
2. Retained the raw request bytes for forwarding and parsed the body separately for gateway decisions.
3. Added `UpstreamClient` backed by one shared `httpx.AsyncClient`.
4. Configured explicit timeouts:
   - Connect: 2 seconds.
   - Read: 5 seconds.
   - Write: 5 seconds.
   - Connection-pool acquisition: 2 seconds.
5. Disabled environment proxy inheritance for the internal hop with `trust_env=False`.
6. Added `TASK2_DOWNSTREAM_URL`, defaulting to `http://127.0.0.1:8001`.
7. Preserved request IDs, including numeric `0` and string IDs.
8. Converted downstream connection failures, HTTP failures, invalid JSON, and non-object JSON into:

```json
{
  "jsonrpc": "2.0",
  "id": "original-id",
  "error": {
    "code": -32603,
    "message": "Downstream service unavailable"
  }
}
```

9. Ensured internal hostnames, ports, HTTPX exception names, upstream bodies, and tracebacks never enter client responses.

### Phase 1 validation

- `tools/list` round-tripped through both services.
- `tools/call` returned the downstream result.
- IDs `0`, `8`, and `"request-7"` were preserved.
- Downstream HTTP 500, malformed JSON, array JSON, and unavailability returned safe `-32603` errors.
- Malformed client JSON and MCP batches were rejected without forwarding.
- Six Phase 1 tests passed, plus all Task 1 tests.

### Phase 1 commit

```text
9f3ac8e feat: add transparent MCP proxy forwarding
```

## Phase 2: Authorization boundary

### Objective

Resolve Bearer credentials to roles and block unauthorized privileged tool calls before forwarding.

### Authentication behavior

The demo token map is intentionally static:

| Bearer token | Subject | Role |
|---|---|---|
| `token-admin-001` | `demo-admin` | `admin` |
| `token-viewer-001` | `demo-viewer` | `viewer` |

The parser requires a case-insensitive `Bearer` scheme, one space, and a known non-empty token. Missing, malformed, unknown, or duplicated credentials resolve to no identity. Tokens are never written to logs.

### Authorization policy

| Method | Tool | Role | Decision |
|---|---|---|---|
| `tools/list` | Not applicable | Any or none | Allow |
| `tools/call` | Ordinary valid name | Any or none | Allow |
| `tools/call` | `admin_*` | `admin` | Allow |
| `tools/call` | `admin_*` | Viewer, unknown, or none | Deny |
| `tools/call` | Missing or malformed name | Any | Deny |
| Other method | Not applicable | Any | Deny |

Tool-name matching for `admin_` is case-insensitive. Valid names are restricted to ASCII letters, digits, underscores, and hyphens. Inputs are not silently trimmed or Unicode-normalized.

### Denial response

An unauthorized privileged call receives HTTP 200 and this protocol-level error:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32001,
    "message": "Unauthorized Tool Call"
  }
}
```

HTTP 200 is deliberate: the HTTP transport completed successfully, while JSON-RPC communicates the application-level failure in a form MCP clients understand.

### Logging

Each decision logs:

- Subject identifier, or `anonymous`.
- Resolved role, or `none`.
- MCP method.
- Validated tool name when available.
- `allow` or `deny` outcome.
- Stable policy reason.

The secret token value is excluded.

### Phase 2 validation

- Viewer calling `admin_reset_key`: blocked with `-32001`.
- Anonymous caller using `admin_reset_key`: blocked with `-32001`.
- Admin calling `admin_reset_key`: forwarded.
- Viewer calling `search_orders`: forwarded.
- Anonymous `tools/list`: forwarded and returned four tools.
- Downstream log contained only the three allowed requests.
- Both denied calls produced zero downstream requests.
- Task 2 suite reached 23 passing tests.

### Phase 2 commit

```text
16d3e10 feat: enforce role-based MCP tool policy
```

## Phase 3: Adversarial hardening

### Objective

Attempt to bypass the authorization boundary using malformed, ambiguous, oversized, or parser-dependent requests.

### Controls added

1. **Case bypass protection:** `ADMIN_RESET_KEY` and `Admin_Reset_Key` are treated as privileged.
2. **Whitespace protection:** names such as ` admin_reset_key` are rejected rather than trimmed.
3. **Unicode protection:** names containing a Cyrillic homoglyph are rejected by the ASCII-only grammar.
4. **Type protection:** list, object, empty, and missing tool names fail closed.
5. **Missing-parameter protection:** absent or malformed `params` fail closed.
6. **Duplicate-key protection:** a custom `object_pairs_hook` rejects repeated JSON object keys at any nesting level.
7. **Duplicate-header protection:** privileged access requires exactly one valid Authorization header.
8. **Batch protection:** top-level JSON arrays are rejected. This prevents an ordinary and privileged request from being smuggled together.
9. **Body-size protection:** request bodies are streamed into a bounded buffer with a default maximum of 65,536 bytes.
10. **Content-Length protection:** invalid, negative, or excessive lengths are rejected before JSON parsing.
11. **Unknown-method protection:** the final policy fails closed on methods other than `tools/list` and `tools/call`, returning `-32601` without forwarding.
12. **Strict ID protection:** object, array, and boolean JSON-RPC IDs are rejected; only string, number, or null are accepted.
13. **Media-type protection:** the MCP endpoint requires `application/json`.
14. **Tool-name length protection:** names are limited to 128 ASCII characters.
15. **Response-size protection:** downstream responses are streamed into a bounded buffer, defaulting to 1 MiB.
16. **Diagnostic correlation:** every error returns `X-Request-ID`, which is included in gateway logs with the JSON-RPC ID.

### Why duplicate keys matter

Consider this ambiguous request:

```json
{
  "method": "tools/call",
  "params": {
    "name": "search_orders",
    "name": "admin_reset_key"
  }
}
```

If the gateway uses the first value while the downstream uses the last, the gateway can authorize an ordinary tool while the downstream executes an admin tool. Rejecting duplicate keys removes the parser-differential attack instead of depending on both components making the same undocumented choice.

### Phase 3 bypass results

| Attack | Result | Downstream contacted? |
|---|---|---|
| Exact `admin_` name by viewer | `-32001` | No |
| Uppercase or mixed-case prefix | `-32001` | No |
| Leading whitespace | `-32001` | No |
| Cyrillic homoglyph | `-32001` | No |
| Empty, list, or object name | `-32001` | No |
| Missing name or params | `-32001` | No |
| Duplicate name key | `-32600` | No |
| Two Authorization headers | `-32001` | No |
| Mixed ordinary/admin batch | `-32600` | No |
| Oversized body | `-32600` | No |
| Unknown method | `-32601` | No |
| `administrator_reset` | Allowed as an ordinary name | Yes |

The `administrator_reset` boundary test proves the gateway implements the specified `admin_` prefix rather than over-blocking every name beginning with the letters `admin`.

### Phase 3 commits

```text
a331f3d test: harden gateway against authorization bypasses
fc95cf1 fix: fail closed on unsupported MCP methods
```

## Phase 4: Finish and submission readiness

### Objective

Make the implementation runnable from a clean clone and understandable to a security architect without reading every source file first.

### Work completed

1. Added a concise reviewer README.
2. Added two-command Windows and POSIX clean-clone verification paths.
3. Documented live-service startup and configurable ports.
4. Documented demo credentials and example JSON-RPC calls.
5. Added the complete policy matrix.
6. Added the threat model and tested bypass table.
7. Explained JSON-RPC error mapping and HTTP status behavior.
8. Documented strict parsing, size limits, timeouts, and failure sanitization.
9. Documented static-token, single-downstream, process-local policy, mock-server, observability, and transport limitations.
10. Documented the production direction: verified JWT/JWKS identity, explicit role allowlists, multi-downstream routing, structured auditing, TLS or mTLS, and network isolation.
11. Updated the root README to link Task 2 and provide its quick start.

### Clean-clone results

The repository was cloned into previously unused temporary directories. A fresh virtual environment was created and populated only from `requirements.txt`.

| Platform | Task 2 | Task 1 regression |
|---|---:|---:|
| Windows x64, Python 3.11 | 54 passed | 14 passed |
| Ubuntu ARM64 | 54 passed | 14 passed |

### Phase 4 commit

```text
4396538 docs: add Task 2 policy and threat model
```

## 7. End-to-end request flows

### Allowed ordinary tool call

1. Client sends `tools/call` for `search_orders`.
2. Gateway reads the body under the configured size limit.
3. Gateway parses JSON and rejects ambiguity.
4. Credential resolves to viewer, admin, or no role.
5. Policy validates the name and determines it is not privileged.
6. Gateway forwards the original raw request bytes.
7. Downstream logs and executes the tool.
8. Gateway validates the downstream response is a JSON object.
9. Gateway returns the downstream JSON-RPC response.

### Allowed admin tool call

1. Client supplies `Authorization: Bearer token-admin-001`.
2. The token resolves to `demo-admin` with role `admin`.
3. Tool name matches the `admin_` prefix.
4. Policy allows the request.
5. Downstream receives and executes it.

### Denied privileged call

1. Viewer, anonymous, malformed, or unknown identity requests an `admin_` tool.
2. Gateway parses and validates the request.
3. Policy returns `admin_role_required`.
4. Gateway immediately returns `-32001` with the original ID.
5. The forwarding function is never called.
6. Downstream call count remains zero.

### Downstream failure

1. Policy allows a request.
2. Downstream is unavailable, times out, returns HTTP failure, malformed JSON, or a JSON array.
3. `UpstreamClient` raises the internal `UpstreamFailure` abstraction.
4. Detailed failure information remains in server logs.
5. Client receives only `-32603 Downstream service unavailable`.

## 8. Error contract

| Code | Message | Situation |
|---:|---|---|
| `-32700` | `Parse error` | Malformed JSON. |
| `-32600` | `Invalid Request` | Wrong top-level type, duplicate keys, invalid envelope, batch, or excessive body. |
| `-32601` | `Method not found` | Method outside the gateway's supported allowlist. |
| `-32001` | `Unauthorized Tool Call` | Privileged, missing, malformed, or ambiguous tool call denied by policy. |
| `-32603` | `Downstream service unavailable` | Connection, timeout, HTTP, or downstream-response failure. |

## 9. Configuration

| Variable | Default | Purpose |
|---|---|---|
| `GATEWAY_PORT` | `8000` | Port used by `run_both.sh` for the gateway. |
| `DOWNSTREAM_PORT` | `8001` | Port used by `run_both.sh` for the downstream. |
| `TASK2_DOWNSTREAM_URL` | `http://127.0.0.1:8001` | Direct downstream base URL used by the gateway. |
| `TASK2_MAX_BODY_BYTES` | `65536` | Maximum accepted JSON-RPC request size. |
| `TASK2_MAX_RESPONSE_BYTES` | `1048576` | Maximum downstream response size read by the gateway. |
| `TASK2_UPSTREAM_READ_TIMEOUT` | `5.0` | Downstream response read timeout in seconds. |

## 10. Run and verify

### Windows PowerShell

From the repository root:

```powershell
py -3.11-64 -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest task2\tests -q
```

Expected result:

```text
54 passed
```

### Linux or macOS

```bash
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest task2/tests -q
```

### Start both live services

On Windows PowerShell:

```powershell
.\task2\scripts\run_both.ps1
```

On Linux, macOS, Git Bash, or WSL:

```bash
. .venv/bin/activate && bash task2/scripts/run_both.sh
```

If the default ports are occupied:

```bash
GATEWAY_PORT=18000 DOWNSTREAM_PORT=18001 bash task2/scripts/run_both.sh
```

### Example tool discovery

```bash
curl -s http://127.0.0.1:8000/mcp \
  -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

### Example denied call

```bash
curl -s http://127.0.0.1:8000/mcp \
  -H 'content-type: application/json' \
  -H 'authorization: Bearer token-viewer-001' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"admin_reset_key","arguments":{}}}'
```

Expected error code: `-32001`.

### Example allowed admin call

```bash
curl -s http://127.0.0.1:8000/mcp \
  -H 'content-type: application/json' \
  -H 'authorization: Bearer token-admin-001' \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"admin_reset_key","arguments":{}}}'
```

Expected downstream text: `Executed admin_reset_key`.

## 11. Security and design decisions

### Static tokens instead of an unsigned JWT

A static map is explicitly within assessment scope and makes the simplification visible. An unsigned or unverified JWT would appear more realistic while introducing a serious authentication vulnerability. Production should verify signatures through a trusted JWKS endpoint and enforce issuer, audience, expiry, and not-before claims before reading roles or scopes.

### Authorization before forwarding

The policy decision is made before `UpstreamClient.forward` is invoked. Tests use a recording upstream and assert an empty call list for every denied request. This proves the gateway did not merely hide the downstream response after a privileged side effect had already occurred.

### Fail closed on unknown methods

Only `tools/list` and `tools/call` are supported. Unknown methods return `-32601` locally. This is less compatible with additional MCP capabilities, but it avoids silently forwarding a method the gateway has no policy for.

### Prefix policy is intentionally limited

The `admin_` prefix is required by the assessment, but it is not the recommended production design. A privileged downstream tool named incorrectly would bypass classification. Production should use gateway-owned tool metadata or an explicit identity-to-tool allowlist so the protected service does not define its own security category through naming alone.

### HTTP 200 for authorization denial

The HTTP exchange succeeded and produced a valid JSON-RPC response. Returning the assessment's `-32001` error in an HTTP 200 response keeps the failure within the MCP/JSON-RPC contract. HTTP authentication status codes would be appropriate for a transport-level authentication scheme, but the implemented contract is a method-level tool authorization decision.

### Raw body plus parsed policy view

Forwarding the original bytes avoids unnecessarily rewriting valid requests. Parsing a separate representation allows the gateway to authorize the actual wire payload. Duplicate-key rejection ensures the parsed view cannot disagree with the downstream because of first-key versus last-key parser behavior.

## 12. Known limitations and production path

1. **Static identity:** there is no token signature, expiry, revocation, issuer, audience, or external identity provider. Use signed, short-lived tokens verified against JWKS.
2. **Prefix authorization:** classification depends on naming. Replace it with explicit per-role or per-identity tool allowlists owned by the gateway.
3. **One downstream:** there is no server discovery or routing. Add authenticated downstream identities, routing tables, health checks, and isolated connection pools.
4. **Process-local policy:** configuration changes require a deployment. Use centrally managed, versioned policy with audit history.
5. **Local HTTP:** there is no transport encryption. Use TLS or mTLS, restricted egress, and network controls that prevent direct downstream access.
6. **Simple mock MCP server:** the downstream is sufficient for the assessment but does not implement every MCP capability.
7. **No distributed rate limiting:** request-size protection exists, but traffic-volume controls belong at an ingress layer or shared limiter.
8. **Logging only:** production should export structured decisions, denial counts, downstream latency, timeout rate, and failure rate to an observability platform.

## 13. Complete commit history for Task 2

```text
3fac304 feat: scaffold Task 2 gateway services
9f3ac8e feat: add transparent MCP proxy forwarding
16d3e10 feat: enforce role-based MCP tool policy
a331f3d test: harden gateway against authorization bypasses
fc95cf1 fix: fail closed on unsupported MCP methods
4396538 docs: add Task 2 policy and threat model
2842a4e fix: close Task 2 validation gaps
```

The history intentionally preserves the security corrections that changed unknown methods to fail closed and added strict wire validation, bounded upstream responses, live-process integration coverage, correlated diagnostics, and native Windows startup.

Four deliberate mutation checks were also run after remediation. Disabling the privileged-prefix rule failed `test_non_admin_cannot_call_privileged_tool`; bypassing the pre-forward denial failed `test_blocks_privileged_call_before_forwarding`; removing duplicate-key detection failed `test_duplicate_name_key_is_rejected_without_forwarding`; and removing the response-size guard failed `test_rejects_downstream_response_over_configured_limit`. Every mutation was reverted and the complete 54-test suite returned green.

## 14. Interview defense checklist

Be prepared to explain these points without reading the source:

1. How the test proves a denied call never reached the downstream.
2. Why an ID value of `0` must not be treated as missing.
3. Why duplicate JSON keys create a parser-smuggling risk.
4. Why two Authorization headers resolve to no identity.
5. Why case-folding is used for `admin_`, while Unicode names are rejected.
6. Why the gateway does not trim a tool name before authorizing it.
7. Why authorization denial uses JSON-RPC `-32001` with HTTP 200.
8. Why unsupported methods now fail closed.
9. Why prefix matching is weaker than an explicit tool allowlist.
10. Why a static map is safer for this assessment than decoding an unverified JWT.
11. How downstream errors are sanitized without losing diagnostic information in logs.
12. Where TLS, mTLS, identity verification, routing, policy distribution, and observability belong in a production deployment.

## 15. Final conclusion

Task 2 satisfies the stated assessment requirements and adds concrete evidence that the security boundary holds under hostile input. The gateway parses JSON-RPC deliberately, makes the authorization decision before forwarding, preserves protocol IDs, blocks unauthorized `admin_` calls with the required `-32001` error, handles downstream failures safely, and proves non-forwarding through automated call-count assertions. The implementation remains intentionally scoped: the static token map, prefix rule, mock downstream, and single-process configuration are documented assessment simplifications rather than hidden production claims.
