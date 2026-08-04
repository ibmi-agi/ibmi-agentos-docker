# Create a New IBM i Agent

> Claude Code prompt. Open Claude Code in this repo and paste:
> `Run docs/create-new-agent.md`

You are creating a new IBM i agent in this AgentOS template. The template ships **six reference agents** (`agents/text2sql_agent.py`, `agents/performance_agent.py`, `agents/security_audit_agent.py`, `agents/library_list_security_agent.py`, `agents/ptf_agent.py`, `agents/sample_data_agent.py`). Use **`agents/performance_agent.py`** as the working model; your new agent should mirror its shape and only diverge where the new domain requires.

The user already has the stack running on `http://localhost:8000` (`RUNTIME_ENV=dev`). Uvicorn hot-reloads on edits inside an existing module, but **registering a new agent module requires `podman compose restart agentos-api`** — see Step 6.

Two phases, with explicit confirmation gates:

- **Phase 1 — Tools.** Decide which toolsets the agent needs. If any are missing, build them (explore with `ibmi` → draft SQL → write YAML → validate) before scaffolding the agent. Full loop: [`docs/write-new-tool.md`](write-new-tool.md).
- **Phase 2 — Agent.** Scaffold the agent module, compose its inline instructions, register it, smoke-test.

Schema/conventions for tool YAMLs live in [`docs/tool-design-reference.md`](tool-design-reference.md). The `ibmi` CLI is the only database utility used in this loop — see [`docs/ibmi-cli.md`](ibmi-cli.md) for setup.

## 0. Preconditions

- Live API: `curl -sSf http://localhost:8000/healthz` returns 200.
- Live MCP server: `curl -sSf http://localhost:3010/healthz` returns 200.
- `.env` has `ANTHROPIC_API_KEY` (or whatever provider `AGENT_MODEL` points at) and `DB2i_HOST` / `DB2i_USER` / `DB2i_PASS`.
- `ibmi` works: `ibmi sql "SELECT CURRENT_DATE FROM SYSIBM.SYSDUMMY1"` returns today's date. Needed for any Phase 1 tool work.

If any are missing, ask the user to fix them — don't proceed against a broken stack.

---

## Phase 1 — Tools

### 1.1 Ask the user (in one consolidated message)

Use `AskUserQuestion` for choice-shaped questions. Ask plain text for free-form fields. Do not interrogate one-at-a-time.

1. **Domain** — what is the agent's job? One sentence. Examples grounded in the SAMPLE schema or extensions thereof:
   - Department / project reporting (SAMPLE-flavored — natural extension of `ibmi-sample`)
   - Job / work management (WRKACTJOB equivalents, subsystem health — needs new tools against `QSYS2`)
   - Security auditing (authorities, `*PUBLIC`, user profiles — needs new tools against `QSYS2`)
   - Backup / journal / spool / message queues — needs new tools
   - Something else — free-form one-sentence description.

2. **SQL safety posture**
   - **Read-only** (default — agent never modifies state). Mirror the SAMPLE Data Agent: every tool sets `security.readOnly: true`.
   - **Read-write with confirmation** — agent can modify, but every DML/DDL call prompts the user. Each modifying tool must be added to `requires_confirmation_tools` in the agent file.
   - **Allow CL / PASE commands** — only when the user explicitly asks. These always require confirmation.

3. **Instruction blocks** — which shared blocks apply? The template ships these in `agents/utils/common.py`, interpolated into the agent's inline f-string `INSTRUCTIONS`:
   - `GUARDRAILS` — almost always include (data redaction, scope limits, prompt-injection defense)
   - `DATA_HANDLING` — query best practices, result presentation, performance awareness. Almost always include
   - `ERROR_HANDLING` — error-narration protocol. Opt in if the agent does many tool calls
   - `AUDIT` — action logging & reasoning visibility
   - `WEB` — web-research guidance (pairs with `*web_tools()`)
   - `USER_CONTEXT` — user-id footer; include last

4. **Slug** — short kebab-case id (e.g. `ibmi-security-audit`). Used as the agent's `id`, in URLs, and in `app/config.yaml`. Propose one based on the domain.

Model defaults to `anthropic:claude-sonnet-4-5` via `AGENT_MODEL` in `agents/utils/common.py`. Override per-agent only if the user explicitly asks.

### 1.2 Decide on toolsets — coverage check

Open `tools/toolsets.json` and surface the existing toolsets to the user in a short table (name, title, brief description, member tool count). The template ships SAMPLE-schema toolsets (`employee_information`, `project_management`, `salary_analysis`, `sample_all`) plus `performance`, `ptf_management`, and the security/library-list toolsets. For each capability the new agent needs, classify:

| State | Action |
|---|---|
| Covered by an existing toolset | Note it; move on |
| Adjacent but incomplete | Plan to **extend** the existing toolset with new tools |
| No matching toolset | Plan to **build a new toolset** in Phase 1.3 |

Show the user a coverage table:

```markdown
| Capability the agent needs | Coverage | Plan |
|---|---|---|
| List employees by department | ✅ `employee_information` toolset | reuse |
| Inspect job log messages | ❌ no toolset | **build new** (`daily_health`) |
| Audit *PUBLIC authority | ❌ no toolset | **build new** (`security_audit`) |
```

Get the user's explicit OK on this plan before doing any tool work. **Do not** proceed to Phase 2 while there are still missing toolsets — the agent file references toolset names, and unknown names won't resolve.

### 1.3 Build any missing tools

For each missing toolset, run [`docs/write-new-tool.md`](write-new-tool.md) **inline, in this same session, not as a handoff**. The short version:

1. **Explore** with `ibmi schemas`, `ibmi tables <schema>`, `ibmi columns <schema> <table>`, `ibmi describe <SCHEMA.OBJECT>` to capture exact column names and types.
2. **Draft & validate SQL** with `ibmi sql "<stmt>"` and `ibmi validate "<stmt>"` — loop on errors.
3. **Preview the tool plan** with a markdown table; wait for explicit user confirmation.
4. **Author the YAML** against [`docs/tool-design-reference.md`](tool-design-reference.md) (§2–§6).
5. **Validate & regenerate** with `uv run python parse_mcp_tools.py` — fix using §9/§10 of the reference doc on failure.
6. **Verify** the MCP server picked it up: `curl -s http://localhost:3010/mcp/tools | jq '.tools[].name' | grep <new>`.

Repeat for each missing toolset. Then return here for Phase 2.

> Phase 1 design rules (from [`docs/tool-design-reference.md`](tool-design-reference.md) §11):
> - Narrow scope beats kitchen sink. Don't build a `run_anything` tool.
> - Parameterize what varies. Use `enum` / `min` / `max` where applicable.
> - Default to read-only. Make `readOnly: false` a deliberate decision.
> - Write AI-facing `description:` text — tell the agent *when* to use the tool, *what* it returns, *how it differs* from siblings.

---

## Phase 2 — Agent

### 2.1 Confirm the toolset wiring

For each toolset (reused or newly built), open `tools/toolsets.json` and confirm:
- The exact toolset name as it'll be passed to `get_toolset("...")`.
- The list of tool names inside it.
- Any tool that needs to be in `requires_confirmation_tools` (modifying tools).

Don't guess.

### 2.2 Generate the agent file

Create `agents/<slug>.py` (kebab → snake_case in filename: `agents/security_audit_agent.py`). Mirror the structure of [`agents/performance_agent.py`](../agents/performance_agent.py) — the canonical reference agent in this template. Instructions are an **inline f-string** (no markdown files), tools are a **module-level list** wiring `MCPTools(... include_tools=get_toolset("..."))`, and the `Agent(...)` config is inlined directly (no shared defaults dict). Required shape:

```python
"""<one-paragraph description of the agent>"""

from agno.agent import Agent
from agno.db.postgres import PostgresDb
from agno.tools.mcp import MCPTools

from agents.utils.common import (
    AGENT_MODEL,
    AUDIT,
    DATA_HANDLING,
    ERROR_HANDLING,
    GUARDRAILS,
    USER_CONTEXT,
    WEB,
)
from agents.utils.tools import get_toolset
from agents.utils.web_context import web_tools
from db.session import db_url

MCP_URL = "http://ibmi-mcp-server:3010/mcp"

AGENT_ID = "ibmi-<slug>"
NAME = "<Display Name>"
DESCRIPTION = """<one-paragraph for the chat picker>"""

INSTRUCTIONS = f"""\
Your mission is to <one-paragraph mission>. Follow these steps:

1. **<Step>** — <what to do, which tools to prefer>
2. **<Step>** — <...>

{GUARDRAILS}

{DATA_HANDLING}

{ERROR_HANDLING}

{AUDIT}

{WEB}

{USER_CONTEXT}\
"""

tools = [
    MCPTools(
        url=MCP_URL,
        transport="streamable-http",
        timeout_seconds=30,
        include_tools=get_toolset("<toolset_name>"),  # from tools/toolsets.json
        # For modifying tools, gate them with HITL confirmation:
        # requires_confirmation_tools=["execute_sql"],
    ),
    *web_tools(),
]

<slug>_agent = Agent(
    id=AGENT_ID,
    name=NAME,
    model=AGENT_MODEL,
    description=DESCRIPTION,
    instructions=INSTRUCTIONS,
    tools=tools,
    markdown=True,
    add_datetime_to_context=True,
    db=PostgresDb(id="agno-storage", db_url=db_url),
    search_session_history=True,
    num_history_sessions=2,
    add_history_to_context=True,
    num_history_runs=3,
    read_chat_history=True,
    read_tool_call_history=True,
    retries=3,
    enable_agentic_memory=True,
)
```

> **text2sql is the one exception.** Instead of a YAML toolset it wires the MCP server's **built-in tools** directly — `include_tools=["list_schemas", "list_tables_in_schema", "get_table_columns", "get_related_objects", "describe_sql_object", "validate_query", "execute_sql"]` (no `get_toolset`). Those tools are enabled in `compose.yaml` via `IBMI_ENABLE_DEFAULT_TOOLS` / `IBMI_ENABLE_EXECUTE_SQL`. See [`agents/text2sql_agent.py`](../agents/text2sql_agent.py).

### 2.3 Compose the inline instructions

The agent's *mission* is the inline `INSTRUCTIONS` f-string in the module itself — there is **no** `agents/instructions/` directory. Mirror [`agents/performance_agent.py`](../agents/performance_agent.py): write the mission steps at the top, then interpolate the shared blocks (`{GUARDRAILS}`, `{DATA_HANDLING}`, `{ERROR_HANDLING}`, `{AUDIT}`, `{WEB}`, `{USER_CONTEXT}`) imported from `agents/utils/common.py`.

Cover, in the mission text:
- **Purpose** (one paragraph) — what the agent does, what it does **not** do.
- **Tool routing** — when to call each toolset, in what order; which tool to prefer for each common question. Be specific about the **newly built** toolsets — without sharp routing language the agent won't reach for them.
- **Output expectations** — table vs. prose, what to summarize, when to recommend follow-ups.
- **Known traps** — IBM i gotchas the agent should be aware of (TR-dependent columns, library list quirks, EBCDIC sort orders, etc.).

Keep the mission tight. The shared blocks already cover safety, data handling, error handling, and audit.

### 2.4 Final preview — confirm before registering

Before editing `app/main.py`, show the user the full registration plan in one table:

```markdown
| Section | Field | Value |
|---|---|---|
| Identity | id / name / slug | ibmi-security-audit / IBM i Security Audit / security-audit |
| Model | model | (inherited) AGENT_MODEL → anthropic:claude-sonnet-4-5 |
| Toolset | include_tools | get_toolset("security_audit") |
| Confirmation | requires_confirmation_tools | execute_sql |
| Instruction blocks | shared | GUARDRAILS, DATA_HANDLING, ERROR_HANDLING, AUDIT, WEB, USER_CONTEXT |
| Files created | new | agents/security_audit_agent.py |
| Files edited | edits | app/main.py (import + agents list), app/config.yaml (quick prompts) |
| Restart needed | podman | podman compose restart agentos-api |
```

Ask: **"Confirm registration plan or request changes?"** Wait for explicit OK.

### 2.5 Register the agent

Edit [`app/main.py`](../app/main.py):

```python
from agents.<slug> import <slug>_agent
# ...
agent_os = AgentOS(
    # ...
    agents=[
        text2sql_agent,
        performance_agent,
        security_audit_agent,
        library_list_agent,
        ptf_agent,
        sample_agent,
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
podman compose restart agentos-api
until curl -sSf http://localhost:8000/healthz > /dev/null; do sleep 0.5; done
curl -s http://localhost:8000/agents | jq '.[] | .id'
```

Confirm the new id appears. Then smoke-test via the AgentOS HTTP API:

```bash
curl -sS -X POST http://localhost:8000/agents/ibmi-<slug>/runs \
  -F message='<a question grounded in the agent'\''s domain>'
```

Or exercise the module directly inside the container:

```bash
podman compose exec agentos-api python -m agents.<module>
```

Check the response: did it use the right toolset(s) — including the newly built one(s)? Did it inspect schema → validate → present → confirm → execute? Did it surface tool errors gracefully?

Iterate at most 2-3 times on the agent's inline `INSTRUCTIONS` in `agents/<slug>.py` before stopping and surfacing the question to the user.

### 2.7 Persist

Don't run `git add` automatically. Summarize what changed — new YAMLs (if any), new agent module (with its inline instructions), edits to `app/main.py` and `app/config.yaml` — and let the user commit.
