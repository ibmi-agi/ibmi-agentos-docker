# CLI Mode — Run Without the MCP Server

By default, every agent in this template reaches IBM i through the `ibmi-mcp-server` container. CLI Mode is an alternate path: agents talk to a local `ibmi` binary that's baked into the container image, with no MCP server in the loop.

Toggle it with one env var:

```bash
IBMI_CLI_MODE=true
```

That's the entire user-facing change. The three reference agents (`text2sql`, `system_health`, `sql_service_guide`) work unchanged in both modes — only the toolkit that backs `ibmi_tools()` differs.

## When to use CLI Mode

| Scenario | MCP Mode | CLI Mode |
|---|---|---|
| Standard multi-user deployment | ✅ default | — |
| Per-user IBM i credentials via `auth/` | ✅ | ❌ bypasses MCP auth |
| Offline development | ❌ MCP server must be reachable | ✅ |
| Single-host "just try the template" | overkill | ✅ |
| Custom YAML tool authoring with `list_tools`/`run_tool` | works | ✅ richer surface |

## What ships in the image

The Dockerfile has a `node-builder` stage that installs `@ibm/ibmi-cli` from npm and copies just the binary + Node runtime into the Python runtime stage. The `ibmi` command is on PATH inside the container; no npm toolchain bleeds into the final image.

Pin or bump the CLI version at build time:

```bash
docker compose build --build-arg IBMI_CLI_VERSION=0.5.2 agentos-api
```

Default is `0.5.1` (matches the MCP server's recommended pairing).

## How CLI Mode changes the toolkit

When `IBMI_CLI_MODE=true`, `agents.utils.toolsets.ibmi_tools()` returns an `IBMiCLITools` instance instead of `MCPTools` / `LazyMCPTools`. The LLM sees these tools (a richer surface than the MCP tool set):

- **Discovery**: `list_schemas`, `list_tables`, `list_columns`, `describe`, `discover_services`
- **SQL**: `validate_sql`, `validate_and_run_sql`
- **CL commands**: `run_cl` (confirmation-gated, inquiry-verb allowlist)
- **YAML tools**: `list_tools`, `describe_tool`, `run_tool` (browses `tools/*.yaml`)
- **PASE shell**: `run_pase` (opt-in via `enable_pase=True`)

MCP-only kwargs passed to `ibmi_tools()` are silently ignored in CLI mode: `url`, `transport`, `timeout_seconds`, `include_tools`, `requires_confirmation_tools`, `header_provider`. The CLI toolkit manages its own scope (`toolsets=`) and confirmation gating natively.

## Connection configuration

The CLI binary has its own connection config — it does **not** read the template's `auth/` module or the `DB2i_*` env vars used by the MCP server. Configure it once inside the container:

```bash
docker compose exec agentos-api ibmi config add my-system \
    --host your-ibmi-host --user your-ibmi-user --pass your-ibmi-password
docker compose exec agentos-api ibmi config list
```

`ibmi config list` shows the registered systems; the active one is what every `validate_and_run_sql` / `run_cl` call targets.

For persistence across container restarts, mount a host volume at the CLI's config directory (consult the `@ibm/ibmi-cli` README for the exact path; typically `~/.ibmi`).

## Running without the MCP server container

Once CLI Mode is on, the MCP server isn't required at all:

```bash
IBMI_CLI_MODE=true docker compose up -d agentos-api agentos-db
# note: no `ibmi-mcp-server` in the up list
```

The `ibmi-mcp-server` service stays declared in `compose.yaml` for users who want MCP Mode — Compose just doesn't start it unless you ask for it.

## Limitations

- **No multi-user auth.** The `auth/` module (API keys + per-user IBM i credentials) only protects MCP traffic. CLI Mode uses the binary's own connection config, which is shared across all requests on the container. If you need per-user identity, stay on MCP Mode.
- **No `requires_confirmation_tools` knob.** The CLI toolkit decides for itself which tools (`run_cl`, `validate_and_run_sql` with writes, `run_pase`) need confirmation, based on inquiry-verb allowlists and read/write classification.
- **Container restart to flip the mode.** `CLI_MODE` is read at import time in `agents/config.py`. Edit `.env`, then `docker compose restart agentos-api`.

## Where things live

| Concern | File |
|---|---|
| Toolkit implementation | `agents/tools/ibmi_cli/` |
| Env gate | `agents/config.py::CLI_MODE` |
| Factory routing | `agents/utils/toolsets.py::ibmi_tools` |
| Tests (offline, no binary needed) | `tests/tools/test_ibmi_cli.py` |
| Image build for the binary | `Dockerfile` (`node-builder` stage) |
