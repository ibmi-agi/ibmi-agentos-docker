# IBM i AgentOS Template — Conventions

This file is the source of truth for any coding agent (Claude Code, Codex, others) working in this repo. `CLAUDE.md` is a symlink to this file — edit one, both update.

## What this repo is

A starter for building IBM i agents on **Agno AgentOS**:

- **Agents** are Python modules under `agents/` registered explicitly in `app/main.py`. No registry, no autoloader — a literal `agents=[...]` list.
- **Tools** for agents come from the **`ibmi-mcp-server`** container; the agents in the template talk to it via MCP. Tool definitions live in `tools/*.yaml` and compile to `tools/toolsets.json` via `parse_mcp_tools.py`.
- **Storage** is Postgres + pgvector via `agno.db.postgres.PostgresDb`. Sessions, memory, traces, knowledge — all in one place.
- **The runtime stack** is `docker compose up -d` → `agentos-db`, `ibmi-mcp-server`, `agentos-api`. Local dev hot-reloads code under `agents/`, `app/`, `auth/`, `db/`.
- **Auth** is optional. Default is single-tenant (one shared IBM i identity from `.env`). Flip `AUTH_ENABLED=true` and apply `compose.auth.yaml` for per-user multi-tenant auth.

## Repo layout

```
agents/                IBM i agent modules + shared utilities
  text2sql.py          Reference: built-in SQL tools, no toolset YAMLs
  sql_service_guide.py Reference: multi-toolset (sysadmin_*) + core SQL
  system_health.py     Reference: multi-toolset (performance, daily_health) + core SQL
  __init__.py          AGENT_DEFAULTS shared kwargs
  config.py            MCP_URL, SQL tool lists
  instructions/        Per-agent mission markdown
  utils/
    common.py          GUARDRAILS / DOMAIN_RULES / SQL_POLICY / WEB / FORMATTING blocks
    toolsets.py        ibmi_tools() factory — the only way agents touch IBM i MCP
    tools.py           toolsets.json loader
    web_context.py     Parallel.ai ContextProvider (sub-agent synthesizes web research)
    lazy_mcp.py        LazyMCPTools — used only when AUTH_ENABLED=true
app/
  main.py              AgentOS instantiation, literal agent list, web backend lifespan
  settings.py          default_model() — reads DEFAULT_MODEL_ID env
  knowledge.py         Lazy singleton ``ibmi_knowledge`` (PgVector) shared by agents
  config.yaml          chat quick-prompts per agent
knowledge/             Source content for the shared knowledge base
  tables/*.json        Table metadata
  queries/*.sql        Validated example queries with header tags
  business/*.md        Conventions, gotchas, metric definitions
learning/              LearningMachine factory (generic, knowledge OFF by default)
  __init__.py          Re-exports get_learning, LearningConfig, DEFAULT_CONFIG
  factory.py           Slim factory — pass learning=get_learning() to each agent
auth/                  Optional multi-user MCP auth (off by default)
db/                    Postgres + pgvector helpers + embedder factory (Ollama / OpenAI)
tools/                 IBM i tool YAMLs + generated toolsets.json + schema
docs/                  Claude Code lifecycle prompts (see README)
scripts/               Format/validate/dev + railway/* + generate_mcp_keys + load_knowledge
evals/                 Eval cases + runner
cli.py                 Interactive REPL for hitting agents from the host
parse_mcp_tools.py     tools/*.yaml → tools/toolsets.json
compose.yaml           Local stack (db + ollama + mcp + api)
compose.auth.yaml      Overlay that flips on AUTH_ENABLED + MCP_AUTH_MODE=ibmi
```

## Working conventions

### Adding an agent

Use [`docs/create-new-agent.md`](docs/create-new-agent.md). Required structure: mirror one of the three reference agents, register the new id in `app/main.py`'s `agents=[...]` list, add quick prompts to `app/config.yaml`, restart the container.

### Adding tools

Edit a `tools/*.yaml` (schema in `tools/sql-tools-config.schema.json`), then **always**:

```bash
uv run python parse_mcp_tools.py
```

This regenerates `tools/toolsets.json` (which the Python side reads for toolset-name → tool-list resolution). The MCP server itself picks up YAML changes via `YAML_AUTO_RELOAD=true`. Toolsets that don't appear in `toolsets.json` can't be referenced from `ibmi_tools(["..."])`.

Full walkthrough: [`docs/extend-agent.md`](docs/extend-agent.md).

### Model provider

One switch: `DEFAULT_MODEL_ID=<provider>:<id>` in `.env`. The default is `anthropic:claude-sonnet-4-6`. Agno's `agno.models.utils.get_model` handles every provider it knows about (`openai:`, `anthropic:`, `google:`, `groq:`, `ollama:`, …). Set the matching API key for whatever provider you pick.

### IBM i conventions in code

These show up in `agents/utils/common.py::DOMAIN_RULES` and `SQL_POLICY` and apply to **every** agent that uses SQL:

- `FETCH FIRST N ROWS ONLY`, not `LIMIT` — Db2 for i syntax
- `UPPER()` for case-insensitive comparisons on EBCDIC strings
- Fully qualified object names: `SCHEMA.TABLE` (e.g. `QSYS2.ACTIVE_JOB_INFO`)
- Job names as `number/user/name`
- `*PUBLIC` authority levels: `*USE`, `*CHANGE`, `*ALL`, `*EXCLUDE`
- Inspect schema (`describe_sql_object` / `get_table_columns`) **before** writing any column-referencing SQL — Tech Refresh level changes what's available
- Call `validate_query` before `execute_sql`
- Confirm before any destructive op

### Validation gate

Before committing, the following must be green:

```bash
bash scripts/format.sh                        # ruff format
bash scripts/validate.sh                      # ruff check + mypy
uv run python -m evals -v                     # if evals/cases.py has assertions
docker compose up -d && \
  curl -sSf http://localhost:8000/healthz     # the stack actually starts
```

For forks: also run a brand-string scrub — see [`docs/review-and-improve.md`](docs/review-and-improve.md) §1. This template ships generic and should stay generic.

### Don't add (deliberate cuts)

- **No `app/registry.py` / `app/factory.py`** — explicit imports in `app/main.py` only
- **No `learning.learned_knowledge` store** wired by default — the shipped `ibmi_knowledge` (in `app/knowledge.py`) is curated content seeded from `knowledge/`, not extracted from chats. The `learning` module's separate `enable_learned_knowledge` flag stays off; flip it on with `get_learning(LearningConfig(enable_learned_knowledge=True), knowledge=ibmi_knowledge)` if you want extracted learnings to land in the same store
- **No domain-specific learning schemas** — `learning/factory.py::LearningConfig` ships with generic Agno schemas; add your own (e.g. a `Db2InstanceFact` schema) by passing `entity_memory_schema=` to a per-agent `LearningConfig`
- **No Leader/Analyst/Engineer three-role team** — the dash-style team pattern is left to user-built domain teams; the three reference agents are single-form
- **No Slack / Discord / other interfaces in `app/main.py`** — the railway template's Slack hook was removed; add yours when needed
- **No team-member deep-copy variants** — agents are single-form
- **No upstream-fork brand strings or env-var prefixes** (any project name the template was derived from)

### Common edits

| Want to | Do this |
|---|---|
| Add a new agent | Run `docs/create-new-agent.md` in Claude Code |
| Add a new IBM i tool | Edit `tools/*.yaml` → run `parse_mcp_tools.py` → restart MCP server |
| Add knowledge for the agents to search | Drop a file under `knowledge/{tables,queries,business}/` → run `scripts/load_knowledge.py` |
| Change the embedder | Edit `EMBEDDING_PROVIDER`/`EMBEDDING_MODEL` in `.env`, run `scripts/load_knowledge.py --recreate` |
| Change the model | Edit `DEFAULT_MODEL_ID` in `.env`, restart `agentos-api` |
| Switch to multi-user auth | See `docs/auth-optional.md` |
| Deploy to Railway | `bash scripts/railway/up.sh` then `scripts/railway/env-sync.sh` |
| Bump MCP server version | Edit `MCP_SERVER_VERSION` in `.env`, `docker compose pull ibmi-mcp-server`, restart |

## Lifecycle docs (Claude Code prompts)

| File | Purpose |
|---|---|
| `docs/create-new-agent.md` | Socratic walk: domain → toolsets → safety → slug → scaffold → register → smoke test |
| `docs/extend-agent.md` | Add a new `tools/*.yaml`, regen, wire into an agent |
| `docs/improve-agent.md` | Probe-loop hardening from the agent's contract |
| `docs/eval-and-improve.md` | Run `python -m evals`, diagnose failures, fix in scope |
| `docs/review-and-improve.md` | Sweep for drift (stale `toolsets.json`, missing env vars, brand-scrub) |

Plus three reference docs:

| File | Purpose |
|---|---|
| `docs/ibmi-mcp-server.md` | How `tools/*.yaml`, `parse_mcp_tools.py`, and the MCP server fit together |
| `docs/knowledge-base.md` | How `knowledge/`, the embedder, and `scripts/load_knowledge.py` work |
| `docs/auth-optional.md` | How to enable multi-user IBM i credentials |
