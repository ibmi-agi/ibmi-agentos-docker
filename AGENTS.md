# IBM i AgentOS (Docker) — Conventions

This file is the source of truth for any coding agent (Claude Code, Codex, others)
working in this repo. `CLAUDE.md` is a symlink to this file — edit one, both update.

## What this repo is

A starter for building IBM i agents on **Agno AgentOS**, deployed with Docker:

- **Agents** are Python modules under `agents/`, registered explicitly in `app/main.py` —
  no registry, no autoloader, just a literal `agents=[...]` list. Six agents ship:
  `text2sql`, `performance`, `security_audit`, `library_list_security`, `ptf`, `sample`.
- **Tools** come from the **`ibmi-mcp-server`** container; agents reach it over MCP.
  - Most agents filter a YAML-defined **toolset**: tool definitions live in `tools/*.yaml`
    and compile to `tools/toolsets.json` via `parse_mcp_tools.py`.
  - The **text2sql** agent instead uses the server's **built-in tools** (the
    `--builtin-tools` / `--execute-sql` flags, set in `compose.yaml` as
    `IBMI_ENABLE_DEFAULT_TOOLS` / `IBMI_ENABLE_EXECUTE_SQL`): `list_schemas`,
    `list_tables_in_schema`, `get_table_columns`, `get_related_objects`,
    `describe_sql_object`, `validate_query`, `execute_sql`.
- **Web research**: every agent gets a `query_web(question)` tool via Agno's
  `WebContextProvider` + `ParallelMCPBackend` (`agents/utils/web_context.py`). The
  FastAPI lifespan in `app/main.py` connects/disconnects the backend. Keyless by
  default; `PARALLEL_API_KEY` raises the rate ceiling.
- **Storage** is Postgres + pgvector via `agno.db.postgres.PostgresDb` — sessions,
  memory, traces in one place.
- **The runtime stack** is `docker compose up -d` → `agentos-db`, `ibmi-mcp-server`,
  `agentos-api`. Local dev hot-reloads code under `agents/`, `app/`, `db/`.

## Repo layout

```
agents/                IBM i agent modules + shared utilities
  text2sql_agent.py    NL -> SQL using the MCP server's built-in tools
  performance_agent.py / security_audit_agent.py / library_list_security_agent.py
  ptf_agent.py / sample_data_agent.py
  utils/
    common.py          AGENT_MODEL + shared instruction blocks (GUARDRAILS, DATA_HANDLING,
                       ERROR_HANDLING, AUDIT, USER_CONTEXT, WEB)
    tools.py           toolsets.json loader (get_toolset / get_toolsets / list_toolsets)
    web_context.py     Parallel web-research provider (query_web)
app/
  main.py              AgentOS instantiation, literal agent list, web lifespan
  config.yaml          chat quick-prompts per agent id
db/                    Postgres helpers (url.py, session.py)
evals/                 Eval suite (cases.py; run with `python -m evals`)
tools/                 IBM i tool YAMLs + generated toolsets.json + schema
docs/                  Agent-authoring lifecycle prompts + reference docs
.agents/skills/        Coding-agent workflows (/setup-platform, /create-agent, /extend-agent,
                       /improve-agent, /create-evals, /eval-and-improve, /review-and-improve);
                       .claude/skills symlinks here
scripts/               format / validate / generate_requirements / venv_setup / build_image
parse_mcp_tools.py     tools/*.yaml -> tools/toolsets.json
compose.yaml           Local stack (db + mcp + api)
compose.prod.yaml      Production override (no bind mount/reload, loopback db + mcp)
```

## Working conventions

### Adding an agent

Mirror an existing agent module (e.g. `agents/performance_agent.py`): module-level
`AGENT_ID`/`NAME`/`DESCRIPTION`, an inline f-string `INSTRUCTIONS` composing the shared
blocks from `common.py` (`{GUARDRAILS} {DATA_HANDLING} {ERROR_HANDLING} {AUDIT} {WEB}
{USER_CONTEXT}`), a `tools=[MCPTools(...include_tools=get_toolset("..."))] + *web_tools()`
list, and a single `Agent(...)`. Register the instance in `app/main.py`'s `agents=[...]`,
add quick prompts to `app/config.yaml`, restart `agentos-api`. The
[`create-agent`](.agents/skills/create-agent/SKILL.md) skill runs this loop end to end;
[`docs/create-new-agent.md`](docs/create-new-agent.md) is the long-form field manual.

### Adding tools

Edit a `tools/*.yaml` (schema in `tools/sql-tools-config.schema.json`), then **always**:

```bash
uv run python parse_mcp_tools.py
```

This regenerates `tools/toolsets.json` (the Python side reads it for toolset-name →
tool-list resolution). The MCP server picks up YAML changes via `YAML_AUTO_RELOAD=true`.
Toolsets that don't appear in `toolsets.json` can't be referenced from `get_toolset(...)`.

### Model provider

One switch: `AGENT_MODEL=<provider>:<id>` in `.env` (default `anthropic:claude-sonnet-4-5`);
`AGENT_TEAM_MEMBER_MODEL` for lighter sub-agents. Agno's `agno.models.utils.get_model`
handles every provider it knows (`openai:`, `anthropic:`, `google:`, `groq:`, `ollama:`,
…). Set the matching API key.

### IBM i conventions in code

Reused across SQL agents (see `agents/utils/common.py::DATA_HANDLING`):

- `FETCH FIRST N ROWS ONLY`, not `LIMIT` — Db2 for i syntax
- `UPPER()` for case-insensitive comparisons on EBCDIC strings
- Fully qualified object names: `SCHEMA.TABLE` (e.g. `QSYS2.ACTIVE_JOB_INFO`)
- Inspect schema (`get_table_columns` / `describe_sql_object`) **before** writing any
  column-referencing SQL — Tech Refresh level changes what's available
- Call `validate_query` before `execute_sql`; confirm before any destructive op

### Evals

The suite lives in [`evals/`](evals/) and runs on agno's eval runner: each `Case` in
`evals/cases.py` probes a live agent and is judged by `AgentAsJudgeEval` (`criteria`)
and/or `ReliabilityEval` (`expected_tool_calls`). Cases run the agents **in-process on
the host** against the live stack — they need `agentos-db` and `ibmi-mcp-server` up, a
model key in `.env`, and real IBM i credentials; every case runs real (read-only) SQL
against the configured system, so run the suite deliberately, not on a schedule. The
runner defaults `MCP_URL` to `http://localhost:3010/mcp` for host-side runs.

```bash
source .venv/bin/activate
python -m evals --tag smoke     # fast core: schema discovery, status, injection, PTF
python -m evals --tag release   # all cases
python -m evals --name <case>   # one case
```

Keep new cases read-only by construction (the shipped ones are), and tag them `smoke`
(fast core) or `release` (everything). The LLM judge follows `AGENT_MODEL`; set
`EVALS_JUDGE_MODEL` to use a different judge. Results log to Postgres via `eval_db`
and are visible at os.agno.com.

Two skills work this suite from opposite ends: to author coverage — especially for
agents you build, which start with none — run
[`/create-evals`](.agents/skills/create-evals/SKILL.md); to diagnose failures and fix
in scope, run [`/eval-and-improve`](.agents/skills/eval-and-improve/SKILL.md).

### Running in production

```bash
docker compose -f compose.yaml -f compose.prod.yaml up -d --build
```

[`compose.prod.yaml`](compose.prod.yaml) drops the dev bind mount and hot reload,
turns off debug logging, and rebinds Postgres **and** the ibmi-mcp-server to loopback
so neither is internet-reachable. This template ships no auth layer (see the deliberate
cuts below), so network posture is the security boundary: keep port 8000 private (LAN,
VPN, or an authenticating reverse proxy), and set a strong `DB_PASS` in `.env`. Needs
Docker Compose v2.24.4+ for the `!reset`/`!override` merge tags.

### Validation gate

Before committing, all of these must be green:

```bash
bash scripts/format.sh                      # ruff format
bash scripts/validate.sh                    # ruff check + mypy + tool YAML schema validation
docker compose up -d && \
  curl -sSf http://localhost:8000/health    # the stack actually starts
```

### Don't add (deliberate cuts)

- **No `app/registry.py` / `app/factory.py`** — explicit imports in `app/main.py` only
- **No CLI** — drive agents via the AgentOS API / control plane, not a host REPL
- **No auth layer** — single-tenant; the MCP server uses one shared IBM i identity from `.env`
- **No knowledge / learning scaffolding** — keep the template minimal; add what you need
  (the eval suite in `evals/` is the one exception — kept small and read-only)
- **No team-member deep-copy variants** — agents are single-form

## Working with coding agents

Dev-time **coding-agent workflows** live in [`.agents/skills/`](.agents/skills/) — the
vendor-neutral home for coding-agent assets, mirroring how `CLAUDE.md` symlinks to
`AGENTS.md`. `.claude/skills` is a committed symlink into it, so Claude Code picks the
skills up on every clone with no setup step; other harnesses (Codex, Cursor, …) can
symlink the same folder. (Windows needs developer mode or `core.symlinks=true` for the
symlink to materialize.) Claude-specific config like `.claude/settings.json` stays a
real file in `.claude/`.

- **`/setup-platform`** — fresh clone to a running platform: Podman check (guided
  install of podman + podman-compose if missing), `.env` (model key + IBM i
  credentials), boot the three containers, prove a real agent answer against the
  user's IBM i, connect the AgentOS UI.
- **`/create-agent`** — add a new IBM i agent: design/build its SQL toolset with the
  `ibmi` CLI, scaffold the module, register it, smoke-test it live.
- **`/extend-agent`** — you drive. Add a tool or toolset, add a capability, refine
  `INSTRUCTIONS`, fix a known bug — one verified change per iteration.
- **`/improve-agent`** — Claude drives. Derives probes from the agent's `INSTRUCTIONS`
  and real usage in the database, judges, edits, re-probes. No user input needed.
- **`/create-evals`** — author eval coverage for an agent: map what its instructions and
  shared blocks promise, mine real sessions for scenarios, write read-only `Case`
  entries with toolset-grounded assertions. How a user's own agents join the suite.
- **`/eval-and-improve`** — run the eval suite, diagnose every failure (agent vs case vs
  tool SQL vs environment), fix in scope until green.
- **`/review-and-improve`** — repo-wide drift sweep (docs vs code vs config).

Invoke a skill by name (`/extend-agent`) or just describe the task — Claude Code matches
it from the skill's `description`. The `docs/*.md` files are the long-form field manuals
the skills lean on (tool YAML schema, `ibmi` CLI setup, worked examples).
