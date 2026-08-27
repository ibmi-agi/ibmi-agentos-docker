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
        │ Db2 for i over Mapepire (port 8076 by default)
        ▼
IBM i system (DB2i_HOST)
```

The MCP server image is published at `ghcr.io/ibm/ibmi-mcp-server` and pinned in `.env.example` via `MCP_SERVER_VERSION`.

## The `tools/` directory

The template ships several tool YAMLs — `tools/employee-info.yaml` (SAMPLE-schema employee/department/project toolsets), `tools/performance.yaml`, `tools/security-ops.yaml`, `tools/library-list-security.yaml`, and `tools/ptf_tools.yaml`. Add more `tools/*.yaml` files as you grow an agent's surface; see [`write-new-tool.md`](../.agents/skills/create-agent/references/write-new-tool.md) for the authoring loop.

> The `ibmi-text2sql` agent is the exception: it uses the MCP server's **built-in** tools (`list_schemas`, `list_tables_in_schema`, `get_table_columns`, `get_related_objects`, `describe_sql_object`, `validate_query`, `execute_sql`), enabled in `compose.yaml` via `IBMI_ENABLE_DEFAULT_TOOLS` / `IBMI_ENABLE_EXECUTE_SQL`. It does not load a YAML toolset.

Every file under `tools/` is one of:

| File | Purpose |
|---|---|
| `*.yaml` | Tool & toolset definitions — the input. Edit these. |
| `toolsets.json` | Generated index of toolset name → tool list. Don't hand-edit |

The JSON Schema the YAMLs validate against is **not stored in this repo** — the validation script downloads it fresh from the ibmi-mcp-server repo on every run and discards it, so it can never go stale.

### YAML shape (minimal)

```yaml
sources:
  ibmi-sample:
    host: ${DB2i_HOST}
    user: ${DB2i_USER}
    password: ${DB2i_PASS}
    port: ${DB2i_PORT:-8076}

tools:
  list_employees_by_department:
    source: ibmi-sample
    description: List employees in a given department.
    statement: |
      SELECT EMPNO, FIRSTNME, LASTNAME, SALARY
      FROM SAMPLE.EMPLOYEE
      WHERE WORKDEPT = :workdept
      FETCH FIRST :row_limit ROWS ONLY
    parameters:
      - name: workdept
        type: string
        required: true
      - name: row_limit
        type: integer
        default: 50
    security:
      readOnly: true

toolsets:
  sample_data:
    title: SAMPLE Data
    description: Schema discovery + employee data for the Db2 for i SAMPLE library.
    tools:
      - list_employees_by_department
```

Three things to know:

1. **`source`** — the connection definition. The template's single source is `ibmi-sample`, parameterized from env vars. Every tool references the same source.
2. **`security.readOnly: true`** — the server validates that the statement is read-only. Modifying tools (UPDATE, DELETE, CL commands) must omit this or set `false` and pair it with `annotations.destructiveHint: true`.
3. **`toolsets`** — groups of tools agents can grab as a unit (via `MCPTools(... include_tools=get_toolset("sample_data"))`). Tools can belong to multiple toolsets if they're useful in multiple contexts.

Full schema: [`sql-tools-config.json` in the ibmi-mcp-server repo](https://raw.githubusercontent.com/IBM/ibmi-mcp-server/refs/heads/main/packages/server/src/ibmi-mcp-server/schemas/json/sql-tools-config.json) — validate against it with `uv run python .agents/skills/create-agent/scripts/validate_tools.py tools/<file>.yaml`.

## The validation + `parse_mcp_tools.py` pipeline

```
tools/*.yaml  ──▶  validate_tools.py  ──▶  parse_mcp_tools.py  ──▶  tools/toolsets.json
                          │
                          └──▶ downloads the live sql-tools-config schema,
                               validates in memory, discards it
```

Two steps, two scripts:

1. **`validate_tools.py`** (`.agents/skills/create-agent/scripts/`) downloads the authoritative JSON Schema from the ibmi-mcp-server repo, validates every given YAML against it, and discards the schema — bad YAML errors out with the offending path and message.
2. **`parse_mcp_tools.py`** extracts `toolsets:` sections, flattens each to `{toolset_name: {tools: [...], source: "...", title: "...", ...}}`, and writes `tools/toolsets.json`.

Agents load this manifest via `agents/utils/tools.py::get_toolset(name)`. So **whenever you edit a YAML, validate and regenerate**:

```bash
uv run python .agents/skills/create-agent/scripts/validate_tools.py tools/
uv run python parse_mcp_tools.py
```

The compose file mounts `./tools` into the MCP server with `YAML_AUTO_RELOAD=true`, so the MCP server picks up **edits to existing YAMLs** within a few seconds. A **new `tools/*.yaml` file** needs the container recreated — the server caches the file set at startup, the watcher misses new files, and the cache survives a plain restart — then an `agentos-api` restart, because `MCPTools` fetches the tool list once at agent startup:

```bash
podman compose up -d --force-recreate ibmi-mcp-server
until curl -sSf http://localhost:3010/healthz > /dev/null; do sleep 0.5; done
podman compose restart agentos-api
```

The toolsets.json is read by the Python agents only — they need it regenerated to know the new toolset name exists.

## Bumping `MCP_SERVER_VERSION`

```bash
# 1. Update .env.example
sed -i '' 's/MCP_SERVER_VERSION=v[0-9.]*/MCP_SERVER_VERSION=v0.6.0/' .env.example

# 2. Apply to your .env
sed -i '' 's/MCP_SERVER_VERSION=v[0-9.]*/MCP_SERVER_VERSION=v0.6.0/' .env

# 3. Pull and recreate
podman compose pull ibmi-mcp-server
podman compose up -d ibmi-mcp-server

# 4. Smoke
curl -sSf http://localhost:3010/healthz
```

If the new version breaks a tool YAML (schema changed, validator stricter), `validate_tools.py` will fail and tell you which file — it always validates against the schema on the ibmi-mcp-server repo's `main` branch, so it sees schema changes as soon as they land upstream.

## Exercising an agent

The stack has no host CLI. Drive an agent through the AgentOS HTTP API:

```bash
curl -sS -X POST http://localhost:8000/agents/ibmi-sample/runs \
  -F message='list the tables in SAMPLE'
```

Or run a single agent module directly inside the container:

```bash
podman compose exec agentos-api python -m agents.sample_data_agent
```

The MCP server is single-tenant: it connects with one shared IBM i identity (`DB2i_USER` / `DB2i_PASS` from `.env`) for every request — there is no per-user auth layer.

## Troubleshooting

- **Healthcheck fails**: check `podman compose logs ibmi-mcp-server`. Often it's bad `DB2i_*` creds — the server starts but fails to open the SQL connection on the first request.
- **Tool not showing up**: regenerate `toolsets.json` and check the YAML validated cleanly. If it's a *new* YAML file, `podman compose up -d --force-recreate ibmi-mcp-server` — a plain restart keeps the startup cache (the log line `Registering N cached YAML tools (cache hit)` with the old count is the tell) — then restart `agentos-api`.
- **"Read-only validator rejected statement"**: the SQL has a write or a function the validator considers unsafe. Mark the tool `readOnly: false` and add a `destructiveHint`, then plumb it through `requires_confirmation_tools` in the agent.
- **Slow queries**: `MCP_POOL_QUERY_TIMEOUT_MS` in `compose.yaml` controls the per-query timeout (default 120s).
