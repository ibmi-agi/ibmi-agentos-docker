# ibmi_cli — IBM i CLI Toolkit

Agno `Toolkit` that wraps the `ibmi` binary for database introspection, SQL
execution, CL command dispatch, YAML-defined tool execution, and (opt-in)
PASE shell access. It is the bridge between an Agno agent and a live IBM i
system.

Every tool returns an **`Envelope`** — a `dict[str, Any]` subclass that
stringifies to canonical JSON at the Agno wire boundary, so the LLM sees a
stable shape and Python callers can index fields directly (`env["ok"]`,
`env["data"]`).

## Package Layout

One concern per submodule:

| Module | Responsibility |
|---|---|
| [`_env.py`](./_env.py) | Child-process environment scrubbing (§A) |
| [`envelope.py`](./envelope.py) | `Envelope` type, `PreflightError`, error codes, failure-envelope factories (§B) |
| [`sql.py`](./sql.py) | Pure SQL builders — literal escaping, `QCMDEXC`/`pase_call` wrappers, `SERVICES_INFO` query (§C) |
| [`preflight.py`](./preflight.py) | Pure validators returning `PreflightError \| None` (§D) |
| [`dispatch.py`](./dispatch.py) | `CommandSpec` + CLI envelope parser (§E) |
| [`toolkit.py`](./toolkit.py) | `IBMiCLITools` — the public Agno `Toolkit` class (§F + §G) |

## Envelope Shape

Every tool — successful or failed — returns the same nested shape:

```json
{
  "ok": false,
  "command": "run_sql",
  "error": {"code": "PREFLIGHT_READ_ONLY_VIOLATION", "message": "...", "details": {}},
  "ibmi": {"tool": "run_sql", "elapsed_ms": 12.34, "source": "preflight"}
}
```

`ibmi.source` is one of:

- `preflight` — Python-side validation rejected the call
- `cli` — the `ibmi` binary reported failure in its own envelope
- `runtime` — subprocess never produced a parseable envelope (not found, timeout)
- `python` — synthetic success envelope built inside the toolkit (e.g. `list_tools`)

Error-code prefixes let the LLM branch without string-matching:

- `PREFLIGHT_*` — Python-side mistake (bad args, out-of-scope tool, missing `describe_tool`)
- `RUNTIME_*` — subprocess itself failed (binary missing, timed out)
- `ENVELOPE_*` — CLI spoke but in a malformed shape
- *(unprefixed)* — CLI-origin codes (`SQL_ERROR`, `AUTH_ERROR`, ...) pass through unchanged

## Exposed Tools

Constructed via `IBMiCLITools(system=..., toolsets=[...], enable_pase=False)`.
All tools are registered on the Agno `Toolkit`; `run_sql`, `run_cl`, and
`run_pase` (when enabled) additionally require user confirmation.

| Tool | Purpose |
|---|---|
| `run_sql(statement)` | Execute SQL in read-only mode |
| `validate_sql(statement)` | Parse/validate SQL without executing |
| `run_cl(command, read_only=True)` | Execute a CL command via `QSYS2.QCMDEXC`; read-only mode enforces the inquiry-verb allowlist (`DSP`/`RTV`/`PRT`/`CHK`) |
| `run_pase(pase_command)` | Execute a PASE shell command via `sample.pase_call` (opt-in, absolute paths only) |
| `list_schemas(filter_pattern="")` | Enumerate database schemas, optional SQL `LIKE` filter |
| `list_tables(schema)` | List tables in a schema |
| `list_columns(schema, table)` | List columns for a table |
| `describe(object_name, object_type="TABLE")` | Generate DDL for a database object |
| `discover_services(service_name_filter="")` | Enumerate IBM i SQL Services via `QSYS2.SERVICES_INFO` — agent-facing grep of system capabilities |
| `list_tools()` | List YAML-defined tools curated by this toolkit (zero-arg; see *Curating the tool surface* below) |
| `describe_tool(tool_name)` | Return parameter schema for a YAML-defined tool |
| `run_tool(tool_name, parameters="")` | Execute a named YAML-defined tool (requires prior `describe_tool`) |

### The list → describe → run workflow

`run_tool` is gated by a pre-hook: for any given `tool_name`, the agent MUST
call `describe_tool(tool_name)` first in the same session. If it doesn't,
Agno converts the `AgentRunException` into a recoverable tool failure
(`PREFLIGHT_SCHEMA_NOT_DISCLOSED`) so the model self-corrects:

```
list_tools()
  → describe_tool("SYSTEM_STATUS_ACTIVE")
  → run_tool("SYSTEM_STATUS_ACTIVE", '{"limit": 10}')
```

Successful `describe_tool` calls record the tool name in
`run_context.session_state["ibmi_described"]`, which the pre-hook inspects.

## Curating the tool surface

Scope comes from one of two places, in this precedence order:

1. **`run_context.dependencies`** (builder-registered agents): the
   runtime dict carries `ibmi_toolsets`, `ibmi_extra_tools`, and
   `ibmi_extra_inventory` keys, populated from the component's
   persisted `config.dependencies`. Agno deep-copies it fresh per
   run, so mutations don't leak across runs. This is the per-agent
   dynamic scope and **overrides** the instance defaults whenever
   any of the three keys is present.

2. **`toolsets=[...]` at `__init__`** (static agents like
   `system_health_cli`): a curated list resolved at construction
   time. Used when the shared singleton is built with a scope
   (static agents) or when `run_context.dependencies` doesn't
   include ibmi keys.

`run_tool`, `describe_tool`, and the scope path of `list_tools()`
enforce the same allowlist: names inside the resolved toolsets **or**
in the extras list pass the gate; anything else is rejected with
`PREFLIGHT_TOOL_NOT_IN_SCOPE`. An instance with no toolset scope and
no dependencies is unrestricted (legacy default).

```python
# Static agent — construction-time toolset scope
IBMiCLITools(toolsets=["performance", "daily_health"])

# Shared singleton — no scope at __init__; scope comes per-call
# from run_context.dependencies
IBMiCLITools()
```

`list_tools()` accepts an explicit `tool_path` or `toolsets`
argument. With no arguments, it falls back to the per-call resolved
scope: curated toolsets first (enumerated from `tools/toolsets.json`),
then extras inventory (the flat tool metadata the builder
whitelisted). It errors with `PREFLIGHT_NO_DISCOVERY_SOURCE` when no
source is resolvable and with `PREFLIGHT_AMBIGUOUS_DISCOVERY` when
both `tool_path` and `toolsets` are given at the same time.

Unknown toolset names at `__init__` fail fast with a `ValueError`.
Unknown toolset names in `run_context.dependencies` are silently
ignored by `_resolve_scope` and surface as
`PREFLIGHT_TOOL_NOT_IN_SCOPE` at gate time.

## Security Invariants

The toolkit exists because raw subprocess access to `ibmi` is a footgun.
These rules are enforced structurally, not by convention:

1. **No f-string SQL.** All SQL literals flow through `_escape_sql_literal`
   in [`sql.py`](./sql.py), which doubles single quotes per Db2 rules.
2. **`shell=False`, always.** `subprocess.run` is called with a list of
   args; no shell interpreter ever sees user input.
3. **Scrubbed child env.** `_scrub_child_env` in [`_env.py`](./_env.py)
   builds the child process environment from an allowlist.
4. **Construction-time tool curation.** The scope gate used by
   `run_tool` and `describe_tool` is locked at `__init__` by the
   `toolsets` and `extra_tools` kwargs. The LLM cannot widen its own
   scope at call time.
5. **PASE is opt-in.** `run_pase` is only registered when
   `enable_pase=True`, because `sample.pase_call` can install packages,
   modify the IFS, and run arbitrary scripts — there's no clean
   inquiry-verb allowlist for PASE the way there is for CL.
6. **Absolute-path PASE.** PASE has no `PATH`; `run_pase` rejects
   non-absolute commands at the Python boundary
   (`PREFLIGHT_PASE_RELATIVE_PATH`).
7. **Read-only CL by default.** `run_cl(..., read_only=True)` checks the
   CL verb against `{DSP, RTV, PRT, CHK}` before dispatch
   (`PREFLIGHT_READ_ONLY_VIOLATION`).
8. **Structured logs.** Every dispatch emits one `ibmi_cli.invoke` log
   line with tool name, subcommand, exit code, elapsed time, and error
   code — **never** raw SQL or parameters.

## Dispatch Pipeline

`toolkit.py:_dispatch()` is the single chokepoint for every `ibmi`
invocation:

```
CommandSpec
  → argv assembly (+ --system, --tools, --format json)
  → subprocess.run(shell=False, env=_scrub_child_env(), timeout=IBMI_CLI_TIMEOUT)
  → _parse_cli_envelope(stdout, stderr, returncode) → Envelope
  → structured log line
  → return Envelope
```

Failure modes have dedicated codes: `RUNTIME_CLI_NOT_FOUND`,
`RUNTIME_CLI_TIMEOUT`, `ENVELOPE_PARSE_FAILURE`, `ENVELOPE_MISSING_OK`.

## Construction

```python
from agents.tools.ibmi_cli import IBMiCLITools

tools = IBMiCLITools(
    system="PROD",                      # --system override; falls back to $IBMI_SYSTEM
    toolsets=["performance"],           # scope via named toolsets (static agents)
    enable_pase=False,                  # set True only for operator-tier agents
)
```

`_resolve_tools_path` builds the `--tools` flag for CLI subcommands
that need YAML lookup: explicit `tools_dir` wins, otherwise it returns
a comma-separated list with `PROJECT_TOOLS_DIR` first (where repo YAML
lives) then `USER_TOOLS_DIR` (where the agent builder writes YAML at
runtime).

## Related

- [`docs/agent-builder.md`](../../../docs/agent-builder.md) — agent builder, IBM i CLI toolkit, YAML tools
- [`tools/*.yaml`](../../../tools/) — YAML tool definitions consumed by `run_tool` / `describe_tool`
