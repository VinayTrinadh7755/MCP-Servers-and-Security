# Task 2: MCP Security Gateway

This task implements a small HTTP/JSON-RPC security gateway between an MCP client and a mock downstream MCP service. The gateway resolves a static Bearer token to a role, makes an authorization decision before forwarding, and blocks non-admin callers from invoking tools whose names begin with `admin_`. The mock downstream exposes four tools and logs every request, which makes non-forwarding on a deny path independently observable.

## Clean-clone verification

Python 3.10 or later is required. From the repository root, Windows PowerShell uses two entered lines:

```powershell
py -3.11-64 -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest task2\tests -q
```

On Linux or macOS:

```bash
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest task2/tests -q
```

The expected result is `40 passed`. The tests use in-process HTTP transports and do not require open ports.

## Run the gateway

After installing dependencies, start both services from the repository root:

```bash
. .venv/bin/activate && bash task2/scripts/run_both.sh
```

The gateway listens on `127.0.0.1:8000`; the downstream listens on `127.0.0.1:8001`. Override conflicts without editing code:

```bash
GATEWAY_PORT=18000 DOWNSTREAM_PORT=18001 bash task2/scripts/run_both.sh
```

The gateway's downstream URL can also be set directly with `TASK2_DOWNSTREAM_URL`. `TASK2_MAX_BODY_BYTES` changes the default 65,536-byte request limit.

Demo credentials are deliberately static fixtures, not production secrets:

- `Bearer token-admin-001` resolves to `admin`.
- `Bearer token-viewer-001` resolves to `viewer`.
- An absent, malformed, duplicated, or unknown credential resolves to no role.

Example calls:

```bash
curl -s http://127.0.0.1:8000/mcp -H 'content-type: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
curl -s http://127.0.0.1:8000/mcp -H 'content-type: application/json' -H 'authorization: Bearer token-viewer-001' -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"admin_reset_key","arguments":{}}}'
```

The second call returns HTTP 200 with JSON-RPC error `-32001` and message `Unauthorized Tool Call`. JSON-RPC owns the application error, so the HTTP transport remains successful and MCP clients receive a protocol-native response.

## Authorization policy

The gateway supports only the assessment's two MCP methods and otherwise fails closed.

| Method | Tool name | Caller role | Outcome |
|---|---|---|---|
| `tools/list` | Not applicable | Any or none | Forward |
| `tools/call` | Valid ordinary name | Any or none | Forward |
| `tools/call` | `admin_*`, case-insensitive | `admin` | Forward |
| `tools/call` | `admin_*`, case-insensitive | Viewer, unknown, or none | Block with `-32001` |
| `tools/call` | Missing, non-string, non-ASCII, or malformed | Any | Block with `-32001` |
| Any other method | Not applicable | Any | Block with `-32601` |

Tool names are restricted to ASCII letters, digits, underscores, and hyphens. The gateway does not trim or Unicode-normalize a name because silently transforming an authorization input could make the gateway and downstream authorize different strings.

## Request and failure handling

The raw request body is retained for forwarding, while a parsed copy drives policy. Duplicate JSON object keys are rejected because different parsers may choose different values, creating a request-smuggling gap. JSON-RPC arrays are rejected because MCP no longer supports batching. Request bodies are read incrementally with a fixed upper bound before parsing.

A single shared `httpx.AsyncClient` provides connection pooling and explicit connect, read, write, and pool timeouts. Environment proxy settings are disabled for this internal hop. An unreachable downstream, HTTP failure, malformed downstream JSON, or non-object response becomes `-32603 Downstream service unavailable`; internal URLs, ports, exception types, and response bodies never reach the client. Request IDs, including `0` and strings, are preserved on all paths where the request can be parsed.

## Threat model and bypass results

The protected asset is privileged downstream tool execution. The trust boundary is the gateway's HTTP endpoint. Clients, tokens, JSON bodies, headers, and downstream availability are untrusted; the mock downstream itself is assumed to implement the tool name it advertises.

| Probe | Control | Result |
|---|---|---|
| Uppercase or mixed-case `ADMIN_` | Case-folded prefix comparison | Blocked |
| Leading whitespace | Conservative tool-name grammar | Blocked |
| Cyrillic `а` homoglyph | ASCII-only tool-name grammar | Blocked |
| List, object, empty, or missing name | Type and presence checks | Blocked |
| Missing `params` | Fail-closed policy | Blocked |
| Duplicate `name` JSON keys | Duplicate-key parser hook | Rejected before policy |
| Two Authorization headers | Exactly-one-header requirement | Privileged call blocked |
| Ordinary plus privileged batch | Top-level object requirement | Entire batch rejected |
| Oversized or malformed JSON | Bounded reader and parse handling | Rejected without forwarding |
| Unknown MCP method | Explicit method allowlist | Rejected without forwarding |
| Denied privileged call | Decision precedes upstream call | Upstream call count remains zero |

Tests assert both the client response and the downstream call count. A correct-looking `-32001` response is insufficient if the privileged side effect already happened.

## Design decisions

Static opaque tokens are preferable here to an unsigned JWT. Decoding a JWT without verifying its signature would add realism while creating a known vulnerability. A production deployment would verify a signed JWT against an identity provider's JWKS, enforce issuer, audience, expiry, and not-before claims, then map a verified role or scope claim into policy.

Unknown methods fail closed. This limits compatibility with additional MCP capabilities such as resources or prompts, but it prevents a new or misspelled method from bypassing a gateway that only understands tool authorization. Production support would add methods deliberately with explicit policy and tests.

Prefix matching satisfies the assessment but is a brittle long-term authorization model. It delegates classification to downstream naming conventions: a privileged tool without the prefix becomes accessible. A durable gateway should own an explicit tool allowlist per role or identity, ideally sourced from reviewed policy metadata rather than inferred from a string.

## Trade-offs and next steps

- The token map has no signature verification, expiry, revocation, issuer, or audience. Replace it with verified enterprise identity and short-lived credentials.
- There is one downstream and no discovery or routing. Production would route by server identity with separate connection pools, health checks, and policy per destination.
- Policy and request limits are process-local configuration. Production would load versioned policy centrally and emit auditable policy-version identifiers.
- The mock downstream is intentionally simple and is not a complete MCP implementation. It exists to exercise JSON-RPC forwarding and prove denied calls never arrive.
- Logging records subject, resolved role, method, tool name, result, and reason, but never the token. Production would add request correlation, metrics for deny rate and downstream latency, and structured export to an observability platform.
- HTTP is used locally. A zero-trust deployment should use TLS or mTLS on the internal hop, authenticate the downstream, restrict egress, and prevent clients from reaching the downstream directly.
