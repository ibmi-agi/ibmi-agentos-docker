# Create a New IBM i Agent

> Claude Code prompt. Open Claude Code in this repo and paste:
> `Run docs/create-new-agent.md`

You are creating a new IBM i agent in this AgentOS template. The user already has the stack running locally on `http://localhost:8000` (`RUNTIME_ENV=dev`). Uvicorn hot-reloads on edits inside an existing module, but **registering a new agent module requires `docker compose restart agentos-api`** — see Phase 2, Step 6.

Work in **two phases**, with explicit confirmation gates:

- **Phase 1 — Tools.** Decide which toolsets the agent needs. If any are missing, build them (introspect IBM i → design SQL → validate → preview → author YAML → regenerate) before scaffolding the agent.
- **Phase 2 — Agent.** Scaffold the agent module, write its instruction markdown, register it, smoke-test.

This mirrors the ixora `agent_builder.py` workflow ported to Claude Code: introspect first, validate before writing, preview before committing. Schema/conventions for tool YAMLs live in [`docs/tool-design-reference.md`](tool-design-reference.md) — read it before authoring any new YAML.

## 0. Preconditions

- Live API: `curl -sSf http://localhost:8000/healthz` returns 200.
- Live MCP server: `curl -sSf http://localhost:3010/healthz` returns 200.
- `.env` has `ANTHROPIC_API_KEY` (or whatever provider `DEFAULT_MODEL_ID` points at) and `DB2i_HOST` / `DB2i_USER` / `DB2i_PASS`.
- `ibmi` CLI on the host (`ibmi --version`). Needed for introspection if Phase 1 has to build new tools.

If any are missing, ask the user to fix them — don't proceed against a broken stack.

---

## Phase 1 — Tools

### 1.1 Ask the user (in one consolidated message)

Use `AskUserQuestion` for choice-shaped questions. Ask plain text for free-form fields. Do not interrogate one-at-a-time.

1. **IBM i domain** — what's the agent's job? Examples:
   - Performance / health monitoring (`system_health` is the canonical example)
   - SQL exploration / Db2 schema work (`text2sql` is the canonical example)
   - SQL Services discovery (`sql_service_guide` is the canonical example)
   - Security auditing (authorities, `*PUBLIC`, user profiles)
   - Job / work management (WRKACTJOB equivalents, subsystem health)
   - Backup / journal / spool / message queues
   - Something else — describe in one sentence.

2. **SQL safety posture**
   - **Read-only** (default — agent never modifies state). Use the built-in core SQL tools (`describe_sql_object`, `validate_query`, `execute_sql`) with `execute_sql` in `requires_confirmation_tools`.
   - **Read-write with confirmation** — agent can modify, but every DML/DDL call prompts the user.
   - **Allow CL / PASE commands** — only when the user explicitly says so. These go through `execute_cl_command` / `execute_pase_command` and **always** require confirmation.

3. **Instruction blocks** — which shared blocks apply? The template ships these in `agents/utils/common.py`:
   - `GUARDRAILS` — almost always include (data redaction, scope limits, prompt-injection defense)
   - `DOMAIN_RULES` — IBM i SQL & object conventions (FETCH FIRST, EBCDIC UPPER(), library namespacing). Almost always include
   - `SQL_POLICY` — when the agent has any SQL tools. Include
   - `FORMATTING` — almost always include
   - `ERROR_HANDLING` — opt in if the agent does many tool calls and you want explicit error narration

4. **Slug** — short kebab-case id (e.g. `ibmi-security-audit`). Used as the agent's `id`, in URLs, and in `app/config.yaml`. Propose one based on the domain.

Model defaults to `anthropic:claude-sonnet-4-6` via `app/settings.py::default_model()`. Override per-agent only if the user explicitly asks.

### 1.2 Decide on toolsets — coverage check

Open `tools/toolsets.json` and surface the existing toolsets to the user in a short table (name, title, brief description, member tool count). For each capability the new agent needs, classify:

| State | Action |
|---|---|
| Covered by an existing toolset | Note it; move on |
| Adjacent but incomplete (existing toolset is close but missing tools) | Plan to **extend** the existing toolset with new tools |
| No matching toolset | Plan to **build a new toolset** in Phase 1.3 |

Show the user a coverage table:

```markdown
| Capability the agent needs | Coverage | Plan |
|---|---|---|
| List active jobs | ✅ `performance` toolset | reuse |
| Inspect job log messages | ✅ `daily_health` toolset | reuse |
| Audit *PUBLIC authority on libraries | ❌ no toolset | **build new** (`security_audit`) |
```

Get the user's explicit OK on this plan before doing any tool work. **Do not** proceed to Phase 2 while there are still missing toolsets — the agent file references toolset names, and unknown names won't resolve.

### 1.3 Build any missing tools (run the tool-builder flow inline)

For each missing toolset, run the workflow from [`docs/extend-agent.md`](extend-agent.md) — **inline, in this same session, not as a handoff**. The short version of that loop:

1. Clarify the capability (one consolidated `AskUserQuestion`)
2. **Introspect** IBM i with `ibmi schemas` / `ibmi tables <schema>` / `ibmi columns <schema> <table>` / `ibmi describe <SCHEMA.OBJECT>` to capture exact column names
3. **Draft & validate SQL** with `ibmi validate "<stmt>"` — loop on errors
4. **Preview the tool plan** with a markdown table; wait for explicit user confirmation
5. **Author the YAML** against [`docs/tool-design-reference.md`](tool-design-reference.md) (§2–§6)
6. **Validate & regenerate** with `uv run python parse_mcp_tools.py` — fix using §9/§10 of the reference doc on failure
7. **Verify** the MCP server picked it up: `curl -s http://localhost:3010/mcp/tools | jq '.tools[].name' | grep <new>`

Repeat for each missing toolset. Then return here for Phase 2.

> Phase 1 design rules (lifted from [`docs/tool-design-reference.md`](tool-design-reference.md) §11):
> - Narrow scope beats kitchen sink. Don't build a `run_anything` tool.
> - Parameterize what varies. Use `enum` / `min` / `max` where applicable.
> - Default to read-only. Make `readOnly: false` a deliberate decision.
> - Write AI-facing `description:` text — tell the agent *when* to use the tool, *what* it returns, *how it differs* from siblings.

---

## Phase 2 — Agent

### 2.1 Ground the design in Agno + IBM i docs

If the agent uses any non-trivial Agno feature (custom tool, scheduler, memory tuning, knowledge base), search Agno docs **before** writing code — prefer the `agno-docs` MCP if available, fallback to `https://docs.agno.com/llms.txt`.

For each toolset (reused or newly built), open `tools/toolsets.json` and confirm:
- The exact toolset name as it'll be referenced in `ibmi_tools([...])`
- The list of tool names inside it
- Any tool that needs to be in `requires_confirmation_tools` (modifying tools)

Don't guess.

### 2.2 Generate the agent file

Create `agents/<slug>.py` (kebab → snake_case in filename: `agents/ibmi_security_audit.py`). Mirror the structure of the three reference agents — pick the closest fit:

- [`agents/text2sql.py`](../agents/text2sql.py) — built-in SQL tools only, no toolset YAMLs
- [`agents/sql_service_guide.py`](../agents/sql_service_guide.py) — multiple toolsets + core SQL
- [`agents/system_health.py`](../agents/system_health.py) — multiple toolsets, narrow scope

Required structure:

```python
"""<one-paragraph description of the agent>"""

from __future__ import annotations
from os import getenv

from agno.agent import Agent
from agno.tools.mcp import MCPTools
from agno.tools.parallel import ParallelTools

from agents import AGENT_DEFAULTS
from agents.config import CORE_SQL_TOOLS, SQL_CONFIRMATION_TOOLS  # adjust to needs
from agents.utils.common import (
    DOMAIN_RULES, FORMATTING, GUARDRAILS, SQL_POLICY,
    build_instructions,
)
from agents.utils.toolsets import collect_tools, ibmi_tools
from app.settings import default_model
from db import get_postgres_db

AGENT_ID = "ibmi-<slug>"
NAME = "<Display Name>"
DESCRIPTION = """<one-paragraph for the chat picker>"""

# Web tools (keep or drop based on the agent — domain-internal agents may not need web)
if getenv("PARALLEL_API_KEY"):
    _web: ParallelTools | MCPTools = ParallelTools()
else:
    _web = MCPTools(url="https://search.parallel.ai/mcp", transport="streamable-http")

tools = collect_tools(
    ibmi_tools(
        ["<toolset_a>", "<toolset_b>"],          # from tools/toolsets.json
        include_tools=CORE_SQL_TOOLS,            # optional flat tools
        requires_confirmation_tools=SQL_CONFIRMATION_TOOLS,
    ),
    _web,
)

INSTRUCTIONS = build_instructions(
    GUARDRAILS, DOMAIN_RULES, SQL_POLICY, FORMATTING,
    agent_id=AGENT_ID,  # loads agents/instructions/{AGENT_ID}.md
)

<slug>_agent = Agent(
    id=AGENT_ID,
    name=NAME,
    model=default_model(),
    description=DESCRIPTION,
    instructions=INSTRUCTIONS,
    tools=tools,
    db=get_postgres_db(),
    **AGENT_DEFAULTS,
)
```

### 2.3 Write the instruction markdown

Create `agents/instructions/ibmi-<slug>.md`. This is the agent's *mission* — read by `build_instructions(agent_id=...)` and prepended to the shared blocks.

Required sections:
- **Purpose** (one paragraph) — what the agent does, what it does **not** do
- **Tool routing** — when to call each toolset, in what order; which tool to prefer for each common question. Be specific about the **newly built** toolsets — without sharp routing language the agent won't reach for them.
- **Output expectations** — table vs. prose, what to summarize, when to recommend follow-ups
- **Known traps** — IBM i gotchas the agent should be aware of (TR-dependent columns, library list quirks, EBCDIC sort orders, etc.)

Keep it tight — under 200 lines. The shared blocks already cover safety, formatting, SQL policy.

### 2.4 Final preview — confirm before registering

Before editing `app/main.py`, show the user the full registration plan in one table:

```markdown
| Section | Field | Value |
|---|---|---|
| Identity | id / name / slug | ibmi-security-audit / IBM i Security Audit / security-audit |
| Model | model_id | (inherited) anthropic:claude-sonnet-4-6 |
| Toolsets | new agent will load | `security_audit` (new), `daily_health` (existing) |
| Core tools | include_tools | CORE_SQL_TOOLS |
| Confirmation | requires_confirmation_tools | execute_sql |
| Instruction blocks | shared | GUARDRAILS, DOMAIN_RULES, SQL_POLICY, FORMATTING |
| Files created | new | agents/ibmi_security_audit.py, agents/instructions/ibmi-security-audit.md |
| Files edited | edits | app/main.py (import + agents list), app/config.yaml (quick prompts) |
| Restart needed | docker | docker compose restart agentos-api |
```

Ask: **"Confirm registration plan or request changes?"** Wait for explicit OK. This is the equivalent of ixora's "preview the full configuration before registering" gate.

### 2.5 Register the agent

Edit [`app/main.py`](../app/main.py):

```python
from agents.<slug> import <slug>_agent
# ...
agent_os = AgentOS(
    # ...
    agents=[
        text2sql_agent,
        sql_service_guide_agent,
        system_health_agent,
        <slug>_agent,           # add here
    ],
    # ...
)
```

Edit [`app/config.yaml`](../app/config.yaml) — add 2-3 quick prompts under the new `id`:

```yaml
chat:
  quick_prompts:
    ibmi-<slug>:
      - "<one starter question users will likely ask>"
      - "<another>"
```

### 2.6 Restart and smoke test

```bash
docker compose restart agentos-api
sleep 2 && curl -s http://localhost:8000/agents | jq '.[] | .id'
```

Confirm the new id appears. Then smoke-test:

```bash
uv run python cli.py --agent <slug> --prompt "<a question grounded in the agent's domain>"
```

Check the response: did it use the right toolset(s) — including the newly built one(s)? Did it follow the SQL_POLICY (inspect → validate → present → confirm → execute)? Did it surface tool errors gracefully?

If the smoke test reveals weak behavior, hand off to [`docs/improve-agent.md`](improve-agent.md).

### 2.7 Persist

Don't run `git add` automatically. Summarize what changed — new YAMLs, new agent module, instruction markdown, edits to `app/main.py` and `app/config.yaml` — and let the user commit.
