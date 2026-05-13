# IBM i AgentOS Template

A starter repo for building, improving, and shipping IBM i agents on [Agno AgentOS](https://docs.agno.com). Three reference agents (Text-to-SQL, SQL Service Guide, System Health) are wired up out of the box, and Claude Code prompts under `docs/` drive the full lifecycle — create, improve, extend, eval, review.

The template is designed so a coding agent can read, edit, and improve the platform end-to-end: agent code, traces, tool YAMLs, and docs all live in one repo.

## What you get

| Piece | Where |
|---|---|
| 3 reference agents | `agents/{text2sql,sql_service_guide,system_health}.py` |
| IBM i tools (MCP server) | `tools/*.yaml` → `tools/toolsets.json` via `parse_mcp_tools.py` |
| Postgres + pgvector for sessions, memory, traces, knowledge | `db/` + `compose.yaml` |
| Shared knowledge base (OpenAI embeddings) | `knowledge/` + `app/knowledge.py` + `scripts/load_knowledge.py` |
| Learning module (Agno LearningMachine) | `learning/` |
| Web research via Parallel.ai ContextProvider | `agents/utils/web_context.py` |
| Optional multi-user auth (RSA + AES) | `auth/` + `compose.auth.yaml` |
| Claude Code prompts for the agent lifecycle | `docs/{create-new,improve,extend,eval-and-improve,review-and-improve}-agent.md` |

## Quickstart

**Prerequisites:** Docker (or Podman), an IBM i system reachable from your host, and API keys for your model provider (`ANTHROPIC_API_KEY` by default) and the embedder (`OPENAI_API_KEY` — only needed if you seed the knowledge base).

```bash
git clone <this-repo> ibmi-agentos
cd ibmi-agentos
cp example.env .env
# Edit .env — set DB2i_HOST / DB2i_USER / DB2i_PASS and ANTHROPIC_API_KEY
docker compose up -d
```

Three services come up: `agentos-db` (Postgres + pgvector), `ibmi-mcp-server` (IBM i tools), `agentos-api` (FastAPI + the three reference agents). Verify:

```bash
curl -sSf http://localhost:8000/healthz
curl -sSf http://localhost:3010/healthz
curl -s http://localhost:8000/agents | jq '.[] | .id'
# → ["ibmi-text2sql", "ibmi-sql-service-guide", "ibmi-system-health"]
```

**Optional** — seed the shared knowledge base (table metadata, validated example queries, business glossary) so agents can search it on every turn. Requires `OPENAI_API_KEY` in `.env`:

```bash
uv run python scripts/load_knowledge.py
```

Agents work without this step; they just lose the knowledge-search context. See [`docs/knowledge-base.md`](docs/knowledge-base.md).

Talk to an agent from the terminal:

```bash
uv run python cli.py --agent text2sql --prompt "list schemas containing QSYS"
uv run python cli.py --agent system-health --prompt "what is current CPU utilization?"
uv run python cli.py                                  # interactive REPL
```

Or via HTTP:

```bash
curl -s -X POST -H "Content-Type: application/json" \
    http://localhost:8000/agents/ibmi-text2sql/runs \
    -d '{"input": "describe QSYS2.SYSTABLES"}'
```

## How it fits together

```
cli / curl ──▶ agentos-api ──▶ ibmi-mcp-server ──▶ IBM i (Db2 for i)
                  │                  │
                  │                  ▼
                  │              tools/*.yaml
                  │              (read by MCP server on boot)
                  ▼
              Postgres (agentos-db)
              ├── sessions / memory / traces
              ├── learning  (user_profile, entity_memory, session_context, ...)
              └── ibmi_knowledge (PgVector — OpenAI embeddings)
```

- **Agents** declare themselves in `agents/<name>.py` and register in `app/main.py`'s literal `agents=[...]` list (no registry / autoloader — explicit imports).
- **Tools** live in `tools/*.yaml`, validated and compiled into `tools/toolsets.json` by `parse_mcp_tools.py`. Agents pick toolsets by name via `ibmi_tools(["performance"])`.
- **Knowledge** lives in `knowledge/{tables,queries,business}/`, ingested into PgVector via `scripts/load_knowledge.py`. Every agent searches it on every turn (`search_knowledge=True`).
- **The model provider** is one env var: `DEFAULT_MODEL_ID=anthropic:claude-sonnet-4-6` (default). Swap to OpenAI / Gemini / Groq / Ollama by changing the prefix — Agno's `get_model()` resolves it.

## Designing an IBM i Agent

A new agent is a decision in five dimensions. The lifecycle docs (next section) probe each of these — this section is the mental model.

**1. Domain — what's the job?**
The agent should answer one kind of question well, not many kinds poorly. The three reference agents draw the lines:

- `text2sql` — open Db2 schema exploration ("what columns does QSYS2.SYSTABLES have?")
- `sql_service_guide` — discovery across IBM i SQL Services ("what's the right service for ASP usage?")
- `system_health` — narrow operational diagnostics ("why is CPU pegged?")

Pick a domain where the agent's success criteria are concrete. "Anything IBM i" is not a domain.

**2. Toolsets — reuse or build?**
Tools live in `tools/*.yaml` and compile to `tools/toolsets.json`. Before designing new tools, check `tools/toolsets.json` — most domains already have coverage (`performance`, `daily_health`, `sysadmin_*`). The decision tree:

| Capability needed | Plan |
|---|---|
| Already in a toolset | Reuse it. List the toolset name in `ibmi_tools([...])` |
| Adjacent but missing tools | Extend the toolset — add tools to its YAML file |
| No match | Build a new toolset (one `tools/<name>.yaml`, one toolset per file) |

YAML schema, conventions, and worked examples: [`docs/tool-design-reference.md`](docs/tool-design-reference.md).

**3. Safety posture — read-only by default**
The default and safest stance is read-only: agent uses `describe_sql_object` / `validate_query` / `execute_sql` with `execute_sql` in `requires_confirmation_tools`. Three escalation tiers:

- **Read-only** — no writes, no CL/PASE. Most domains land here.
- **Read-write with confirmation** — agent can run DML/DDL, but every modifying call prompts the user.
- **CL / PASE allowed** — `execute_cl_command` and `execute_pase_command` available; always require confirmation. Only when explicitly needed.

**4. Instruction blocks — what shared rules apply?**
The template ships reusable instruction blocks in `agents/utils/common.py`:

- `GUARDRAILS` — data redaction, scope limits, prompt-injection defense. Include almost always.
- `DOMAIN_RULES` — IBM i SQL conventions (`FETCH FIRST`, EBCDIC `UPPER()`, library namespacing). Include if the agent touches SQL.
- `SQL_POLICY` — inspect → validate → present → confirm → execute. Include if the agent has any SQL tools.
- `FORMATTING` — table vs. prose conventions. Include almost always.
- `ERROR_HANDLING` — opt in if the agent does many tool calls and you want explicit error narration.

These compose with the agent's per-mission markdown at `agents/instructions/<id>.md` (Purpose, Tool routing, Output expectations, Known traps).

**5. Knowledge — does it need grounding context?**
The shared knowledge base under `knowledge/{tables,queries,business}/` is loaded into PgVector and searched on every turn (`search_knowledge=True` in `AGENT_DEFAULTS`). Add files there if the agent benefits from:

- Curated example SQL the agent should pattern-match against (`knowledge/queries/*.sql`)
- Table metadata it should consult before SELECTing (`knowledge/tables/*.json`)
- Business rules, glossary, or IBM i gotchas (`knowledge/business/*.md`)

Rerun `scripts/load_knowledge.py` after adding files.

### What an agent looks like in code

The five decisions above map directly to the agent module. A minimal example (`agents/storage_audit.py`):

```python
from agno.agent import Agent

from agents import AGENT_DEFAULTS
from agents.config import CORE_SQL_TOOLS, SQL_CONFIRMATION_TOOLS
from agents.utils.common import (
    DOMAIN_RULES, FORMATTING, GUARDRAILS, SQL_POLICY, build_instructions,
)
from agents.utils.toolsets import collect_tools, ibmi_tools
from app.knowledge import ibmi_knowledge
from app.settings import default_model
from db import get_postgres_db

AGENT_ID = "ibmi-storage-audit"                                  # (1) domain → slug
NAME = "IBM i Storage Audit Agent"
DESCRIPTION = "Audits ASP usage, library sizes, and storage pools on IBM i."

tools = collect_tools(                                            # (2) toolsets — reused
    ibmi_tools(
        ["performance"],                                          #     a named toolset
        include_tools=CORE_SQL_TOOLS,                             #     describe / validate / execute
        requires_confirmation_tools=SQL_CONFIRMATION_TOOLS,       # (3) safety — confirm on execute_sql
    ),
)

INSTRUCTIONS = build_instructions(                                # (4) shared instruction blocks
    GUARDRAILS, DOMAIN_RULES, SQL_POLICY, FORMATTING,
    agent_id=AGENT_ID,                                            #     + agents/instructions/{AGENT_ID}.md
)

storage_audit_agent = Agent(
    id=AGENT_ID,
    name=NAME,
    model=default_model(),
    description=DESCRIPTION,
    instructions=INSTRUCTIONS,
    tools=tools,
    db=get_postgres_db(),
    knowledge=ibmi_knowledge,                                     # (5) shared knowledge base
    search_knowledge=True,
    **AGENT_DEFAULTS,
)
```

The agent then registers in `app/main.py`'s literal `agents=[...]` list and gets quick prompts in `app/config.yaml`. The three reference agents in `agents/` follow the same shape with progressively more tools.

### From design to scaffold

Once you've answered the five design questions, run [`docs/create-new-agent.md`](docs/create-new-agent.md) in Claude Code. It walks the same five dimensions Socratically, then scaffolds the agent module, writes the instruction markdown, builds any missing toolsets inline (via [`docs/extend-agent.md`](docs/extend-agent.md)), registers the agent in `app/main.py`, and smoke-tests it.

## Working with Claude Code (the intended workflow)

Open the repo in [Claude Code](https://claude.com/claude-code) and paste any of these prompts:

| Prompt | What it does |
|---|---|
| `Run docs/create-new-agent.md` | Socratic walkthrough that scaffolds a new IBM i agent end-to-end |
| `Run docs/extend-agent.md` | Designs and ships a new tool/toolset YAML (introspect → validate SQL → preview → author) and wires it into an agent |
| `Run docs/improve-agent.md` | Probe-loop hardening — derives probes from the agent's contract, runs them, edits until they pass |
| `Run docs/eval-and-improve.md` | Runs the IBM i eval suite (`evals/cases.py`), diagnoses failures, fixes |
| `Run docs/review-and-improve.md` | Sweep for drift (stale `toolsets.json`, missing env vars, deployment hygiene) |

Plus four reference docs:

- [`docs/tool-design-reference.md`](docs/tool-design-reference.md) — YAML schema, conventions, worked examples, common mistakes — read before authoring any `tools/*.yaml`
- [`docs/ibmi-mcp-server.md`](docs/ibmi-mcp-server.md) — how the MCP server, tool YAMLs, and `parse_mcp_tools.py` fit together
- [`docs/knowledge-base.md`](docs/knowledge-base.md) — how `knowledge/`, the embedder, and `scripts/load_knowledge.py` work
- [`docs/auth-optional.md`](docs/auth-optional.md) — how to opt in to multi-user IBM i credentials

## Editing the agents

After editing a Python file under `agents/`, `app/`, `db/`, or `auth/`, the uvicorn reloader picks it up automatically (development mode). After adding a **new** agent file you must restart:

```bash
docker compose restart agentos-api
```

After editing a `tools/*.yaml`:

```bash
uv run python parse_mcp_tools.py     # regenerates tools/toolsets.json
# YAML_AUTO_RELOAD=true in compose, so ibmi-mcp-server picks up YAML changes automatically
```

## Validation gate (before committing)

```bash
bash scripts/format.sh        # ruff format
bash scripts/validate.sh      # ruff check + mypy
uv run python -m evals -v     # eval suite
```

If your fork derives from another project, run a brand-string scrub too — see [`docs/review-and-improve.md`](docs/review-and-improve.md) §1.

The CI workflow at `.github/workflows/validate.yml` runs the same lint + type-check on every push.

## Production deployment

The template targets **Docker** or **Podman** — `compose.yaml` is the source of truth, no platform-specific glue. Bring it up the same way in production as in dev, with a separate env file for secrets:

```bash
docker compose --env-file .env.production up -d
# or
podman compose --env-file .env.production up -d
```

For an image-based deploy (push the API container to a registry, run it next to your IBM i):

```bash
docker build -t your-registry/ibmi-agentos:latest .
docker push  your-registry/ibmi-agentos:latest
```

Then run on the production host with a `compose.yaml` that pulls the published image instead of `build:`. The IBM i MCP server image (`ghcr.io/ibm/ibmi-mcp-server`) is already published — no build step needed.

**Two things you own at deploy time:**

1. **Network** to the IBM i. The MCP server needs Db2-for-i port 8076 reachable. Co-locate it on a host inside the IBM i's network, or open a VPN tunnel.
2. **Where Postgres lives.** `agentos-db` in the template is a single-host container with a local volume — fine for a small deployment, but for HA replace it with a managed Postgres + pgvector (e.g. AWS RDS with the extension enabled, Aiven, etc.) and point `DB_HOST` at it.

## Multi-user auth (opt-in)

Default is single-tenant (one shared IBM i identity from `.env`). For per-user identities:

```bash
echo "AUTH_ENABLED=true" >> .env
bash scripts/generate_mcp_keys.sh
docker compose -f compose.yaml -f compose.auth.yaml up -d
```

Then create an API key and register a connection. Full walkthrough: [`docs/auth-optional.md`](docs/auth-optional.md).

## License

MIT. See `LICENSE`.
