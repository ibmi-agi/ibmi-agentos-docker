# Optional Multi-User MCP Auth

> **Note:** This doc applies only when `IBMI_CLI_MODE=false` (the default). When CLI Mode is on, agents talk to the bundled `ibmi` binary directly and the `auth/` module is bypassed entirely — see [`cli-mode.md`](cli-mode.md). For per-user identity, stay on MCP Mode.

The template ships with a complete optional auth layer in `auth/`. By default it's **off** — every request to the agentos-api uses one shared set of IBM i credentials from `.env`. Flipping `AUTH_ENABLED=true` and applying `compose.auth.yaml` turns on:

1. **API key bearer-token enforcement** — every request to `/agents/*` and other endpoints requires a valid API key
2. **Per-user IBM i credentials** — each API key can register its own IBM i system connection (host + user + password), stored encrypted in Postgres
3. **RSA + AES-256-GCM credential handoff** — when an agent calls the MCP server, the API exchanges the user's stored creds for a short-lived bearer token that the MCP server unwraps to open a Db2 connection under the right profile

This is the right pick when:
- Multiple users share one deployment
- Audit trails must distinguish who ran which query
- IBM i security policy requires per-user identities (not a service account)

## Architecture

```
Browser / CLI ──▶ agentos-api ──▶ ibmi-mcp-server ──▶ IBM i
   (Bearer key)    │   (resolves user creds)     │
                   │   (RSA-wraps + AES-encrypts │
                   │   per-request token)        │
                   └──▶ Postgres                 │
                       api_keys                  │
                       system_connections        │
                       (AES-encrypted creds)     │
```

## Walkthrough

### 1. Install the auth optional dependency group

```bash
uv pip install -e '.[auth]'
```

This adds `cryptography`, `httpx`, and `rich` to your env.

### 2. Generate RSA keys for MCP credential wrapping

```bash
bash scripts/generate_mcp_keys.sh
```

Writes `secrets/private.pem` and `secrets/public.pem`. The `secrets/` directory is git-ignored.

### 3. Generate the auth master keys

```bash
echo "AUTH_MASTER_KEY=$(openssl rand -hex 32)" >> .env
echo "AUTH_ENCRYPTION_KEY=$(openssl rand -hex 32)" >> .env
echo "AUTH_ENABLED=true" >> .env
```

`AUTH_MASTER_KEY` signs the API key hashes. `AUTH_ENCRYPTION_KEY` is the AES key for encrypting IBM i passwords at rest. **Lose either and you lose access** — back them up to a secret manager.

### 4. Bring up the stack with the auth overlay

```bash
docker compose -f compose.yaml -f compose.auth.yaml up -d
```

The overlay flips on `AUTH_ENABLED=true` for the API and `MCP_AUTH_MODE=ibmi` for the MCP server, and mounts the RSA keys.

### 5. Create the first API key

There's no web UI in the template. Use the CLI:

```bash
uv run python -m auth.cli create-key --name "alice's laptop"
```

The output prints the bearer token **once**. Copy it; you cannot retrieve it again.

### 6. Register an IBM i connection for that key

```bash
export AGENTOS_API_TOKEN=sk_abc123
bash scripts/register_connection.sh \
    --name "DEV-LPAR" \
    --host dev.ibmi.example.com \
    --user ALICE \
    --password '<her IBM i password>' \
    --default
```

`--default` marks this connection as the one to use when the user doesn't pick explicitly. Subsequent calls list / update / remove connections via the same script.

### 7. Smoke test

```bash
curl -s -H "Authorization: Bearer $AGENTOS_API_TOKEN" \
    http://localhost:8000/agents | jq '.[].id'
```

Should return the registered agent(s). Without the bearer token:

```bash
curl -i http://localhost:8000/agents | head -1   # 401 Unauthorized
```

Now run an agent — it will use Alice's IBM i creds, not the shared `.env` ones:

```bash
curl -s -X POST -H "Authorization: Bearer $AGENTOS_API_TOKEN" \
    -H "Content-Type: application/json" \
    http://localhost:8000/agents/ibmi-data-agent/runs \
    -d '{"input": "list the tables in SAMPLE"}' | jq
```

## What the auth/ modules do

| Module | Role |
|---|---|
| `auth/middleware.py` | FastAPI middleware that validates the bearer key, resolves the user's connection, sets per-request contextvars |
| `auth/service.py` | API key CRUD: create / revoke / list / verify. SHA-256 hashed at rest with `AUTH_MASTER_KEY` |
| `auth/connections.py` | Connection CRUD: store IBM i creds AES-encrypted with `AUTH_ENCRYPTION_KEY` |
| `auth/mcp_tokens.py` | Fetches the MCP server's RSA public key once at boot, then per-request: encrypts creds with AES, wraps the AES key with RSA, builds the Bearer token the MCP server expects |
| `auth/context.py` | The `mcp_auth_token` / `mcp_connection_id` / `current_api_key_id` contextvars |
| `auth/cli.py` | `python -m auth.cli` — manage API keys |
| `auth/connections_cli.py` | `python -m auth.connections_cli` — manage connections (the `register_connection.sh` wraps this) |
| `auth/router.py`, `auth/connections_router.py` | FastAPI routers wiring the same CRUD over HTTP |

## Limitations of the template's auth

- **No UI** — every admin task is via CLI. Building a web UI against `auth/connections_router.py` is left to the user; the template ships CLI-only.
- **Single-tenant Postgres** — all keys and connections share one schema. Multi-tenant requires more isolation work.
- **No SSO** — bearer keys are local. To integrate with OIDC/SAML, write a middleware that mints a local API key after upstream auth succeeds, then chain it before `APIKeyAuthMiddleware`.

## Disabling auth

Stop the stack, drop `AUTH_ENABLED=true` from `.env` (or set `false`), and bring up without the overlay:

```bash
docker compose down
# edit .env: AUTH_ENABLED=false
docker compose up -d
```

The agent code is unchanged either way — `agents/utils/toolsets.py::ibmi_tools()` checks `AUTH_ENABLED` at agent invocation and routes to the right MCP transport.

## Troubleshooting

- **401 with a valid key**: `AUTH_MASTER_KEY` changed since the key was minted — the hash no longer matches. Revoke and re-issue.
- **403 from the MCP server**: RSA keys mismatch. Regenerate (`scripts/generate_mcp_keys.sh`), recreate the MCP container so it reads the new public key.
- **"No connection registered"**: the API key has no default connection. Run `register_connection.sh --default` or pass `--connection-id` per request.
