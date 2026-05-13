# The IBM i MCP Server

The agents in this template don't talk to IBM i directly. They talk to **`ibmi-mcp-server`** — a small Node service that exposes Db2 for i functions and CL/PASE commands as MCP tools. The server reads `tools/*.yaml` to know which tools to publish.

## Architecture

```
agentos-api (FastAPI, port 8000)
        │
        │ MCP_URL=http://ibmi-mcp-server:3010/mcp
        ▼
ibmi-mcp-server (port 3010)
        │
        │ Db2 for i over JDBC/ODBC (port 8076 by default)
        ▼
IBM i system (DB2i_HOST)
```

The MCP server image is published at `ghcr.io/ibm/ibmi-mcp-server` and pinned in `example.env` via `MCP_SERVER_VERSION`.

## The `tools/` directory

Every file under `tools/` is one of:

| File | Purpose |
|---|---|
| `*.yaml` | Tool & toolset definitions — the input. Edit these. |
| `sql-tools-config.schema.json` | JSON Schema the YAMLs validate against |
| `toolsets.json` | Generated index of toolset name → tool list. Don't hand-edit |

### YAML shape (minimal)

```yaml
sources:
  ibmi-system:
    host: ${DB2i_HOST}
    user: ${DB2i_USER}
    password: ${DB2i_PASS}
    port: ${DB2i_PORT:-8076}

tools:
  list_active_jobs:
    source: ibmi-system
    title: List Active Jobs
    description: Active jobs across all subsystems.
    statement: |
      SELECT job_name, subsystem, cpu_percent, run_priority
      FROM TABLE(QSYS2.ACTIVE_JOB_INFO())
      FETCH FIRST :max_rows ROWS ONLY
    parameters:
      - name: max_rows
        type: integer
        default: 50
    security:
      readOnly: true

toolsets:
  job_management:
    title: Job Management
    description: Inspect and diagnose IBM i jobs.
    tools:
      - list_active_jobs
```

Three things to know:

1. **`source`** — the connection definition. The template's single source is `ibmi-system`, parameterized from env vars. Every tool references the same source.
2. **`security.readOnly: true`** — the server validates that the statement is read-only. Modifying tools (UPDATE, DELETE, CL commands) must omit this or set `false` and pair it with `annotations.destructiveHint: true`.
3. **`toolsets`** — groups of tools agents can grab as a unit (via `ibmi_tools(["job_management"])`). Tools can belong to multiple toolsets if they're useful in multiple contexts.

Full schema: `tools/sql-tools-config.schema.json`.

## The `parse_mcp_tools.py` pipeline

```
tools/*.yaml  ──▶  parse_mcp_tools.py  ──▶  tools/toolsets.json
                          │
                          └──▶ validates against sql-tools-config.schema.json
```

`parse_mcp_tools.py`:
1. Reads every `tools/*.yaml`
2. Validates each against the schema (jsonschema) — bad YAML errors out with line numbers
3. Extracts `toolsets:` sections, flattens each to `{toolset_name: {tools: [...], source: "...", title: "...", ...}}`
4. Writes `tools/toolsets.json`

Agents load this manifest via `agents/utils/tools.py::get_toolset(name)`. So **whenever you edit a YAML, regenerate the JSON**:

```bash
uv run python parse_mcp_tools.py
```

The compose file mounts `./tools` into the MCP server with `YAML_AUTO_RELOAD=true`, so the MCP server picks up YAML changes within a few seconds. The toolsets.json is read by the Python agents only — they need it regenerated to know the new toolset name exists.

## Bumping `MCP_SERVER_VERSION`

```bash
# 1. Update example.env
sed -i '' 's/MCP_SERVER_VERSION=v[0-9.]*/MCP_SERVER_VERSION=v0.6.0/' example.env

# 2. Apply to your .env
sed -i '' 's/MCP_SERVER_VERSION=v[0-9.]*/MCP_SERVER_VERSION=v0.6.0/' .env

# 3. Pull and recreate
docker compose pull ibmi-mcp-server
docker compose up -d ibmi-mcp-server

# 4. Smoke
curl -sSf http://localhost:3010/healthz
```

If the new version breaks a tool YAML (schema changed, validator stricter), `parse_mcp_tools.py` will fail and tell you which file.

## Running outside Docker

For local agent development without the full stack, you can run just the MCP server:

```bash
docker compose up -d ibmi-mcp-server agentos-db
uv run python cli.py --agent text2sql --prompt "list schemas"
```

`cli.py` overrides `MCP_URL` to `http://localhost:3010/mcp` so it can reach the docker-published port from the host.

## Auth modes

The MCP server itself supports two modes:

| Mode | Env | Behavior |
|---|---|---|
| `none` | `MCP_AUTH_MODE=none` (default) | Shared credentials from `.env` (`DB2i_USER`/`DB2i_PASS`). One identity for every request. |
| `ibmi` | `MCP_AUTH_MODE=ibmi` | Each request carries its own encrypted IBM i credentials (RSA-wrapped, AES-encrypted). Per-user identity. |

The `ibmi` mode requires this template's optional auth layer. See [`docs/auth-optional.md`](auth-optional.md).

## Troubleshooting

- **Healthcheck fails**: check `docker compose logs ibmi-mcp-server`. Often it's bad `DB2i_*` creds — the server starts but fails to open the SQL connection on the first request.
- **Tool not showing up**: regenerate `toolsets.json`, restart the MCP server, check the YAML validated cleanly.
- **"Read-only validator rejected statement"**: the SQL has a write or a function the validator considers unsafe. Mark the tool `readOnly: false` and add a `destructiveHint`, then plumb it through `requires_confirmation_tools` in the agent.
- **Slow queries**: `MCP_POOL_QUERY_TIMEOUT_MS` in `compose.yaml` controls the per-query timeout (default 120s).
