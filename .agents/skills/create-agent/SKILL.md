---
name: create-agent
description: Add a new IBM i agent to this AgentOS. Two phases — design the SQL toolset the agent needs (building missing tools with the ibmi CLI), then scaffold agents/slug_agent.py, register it in app/main.py, add its manifest entry, restart the container, and smoke-test it live. Use whenever the user wants to add or create a new agent.
---

# Create a New IBM i Agent

> _**Coding-agent workflow** — a `/slash-command` your coding agent (Claude Code, Codex, others) runs while developing this repo. Invoke it by name (e.g. `/create-agent`) or describe the task and it triggers automatically._

You are creating a new IBM i agent in this AgentOS. The template ships six reference agents; use [`agents/performance_agent.py`](../../../agents/performance_agent.py) as the working model — your new agent should mirror its shape and only diverge where the new domain requires.

Agents here get their IBM i tools from the **`ibmi-mcp-server`** container: tool definitions live in [`tools/*.yaml`](../../../tools/), compile to `tools/toolsets.json`, and agents filter them with `include_tools=get_toolset("...")`. So creating an agent is two phases: **tools first, then the agent**.

## 0. Preconditions

- Live API: `curl -sSf http://localhost:8000/health` returns 200.
- Live MCP server: `curl -sSf http://localhost:3010/healthz` returns 200.
- `.env` has a model key (`ANTHROPIC_API_KEY` by default) and `DB2i_HOST` / `DB2i_USER` / `DB2i_PASS`.
- If Phase 1 tool work is likely: `ibmi sql "SELECT CURRENT_DATE FROM SYSIBM.SYSDUMMY1"` returns today's date ([`docs/ibmi-cli.md`](../../../docs/ibmi-cli.md) covers setup).

If the stack isn't up, ask the user to run `podman compose up -d --build` and wait. Don't proceed against a broken stack.

## 1. Find the agent worth building

**Be self-driving: ask only what needs a human, decide the rest, and say what you decided.** Two exchanges is the target — one to understand the job, one to confirm what you'll build. The slug, the instruction blocks, and the toolset composition are your calls, not the user's.

Use the coding agent's structured user-input control when available (Claude Code's `AskUserQuestion`, Codex's user-input tool, or an equivalent) for choice-shaped questions; plain prompts for free-form answers.

**If they already named an agent** — "build me a job-queue monitor" is a complete brief. Ask nothing. Design it, state what you're building in one message, and start. Only pause if something is genuinely missing (a toolset that has to be built needs Phase 1's plan confirmation).

**If they want guidance** — open with one question: *what do you check on this system every week that you'd rather hand off?* Grounded IBM i domains to steer with: job/work management (WRKACTJOB equivalents, subsystem health), message queues and job logs, backup/journal status, storage and ASP usage, spool files, user profiles and authorities. Dig once for specifics, then propose **one agent you recommend** plus a fallback — not a menu.

**Decide these yourself:**

| Decision | How you decide it |
|---|---|
| **Slug** | Kebab-case, `ibmi-` prefixed like the shipped agents (`ibmi-job-monitor`). State it, don't ask. |
| **SQL safety posture** | **Read-only is the default** — every tool sets `security.readOnly: true`. Only go read-write if the user's job genuinely requires it; each modifying tool then goes in `requires_confirmation_tools` on the agent (see [`agents/text2sql_agent.py`](../../../agents/text2sql_agent.py) gating `execute_sql`). |
| **Instruction blocks** | From [`agents/utils/common.py`](../../../agents/utils/common.py): `GUARDRAILS`, `DATA_HANDLING`, `ERROR_HANDLING`, `AUDIT`, `WEB`, `USER_CONTEXT`. Default to all six — that's what the shipped agents do. |
| **Model** | `AGENT_MODEL` env default (`anthropic:claude-sonnet-4-5`). Override only if the user asks. |
| **Web research** | Include `*web_tools()` + the `{WEB}` block by default — every shipped agent carries it. |

## 2. Phase 1 — toolsets

Open [`tools/toolsets.json`](../../../tools/toolsets.json) and map each capability the agent needs to a toolset:

| State | Action |
|---|---|
| Covered by an existing toolset | Note it; move on |
| Adjacent but incomplete | **Extend** the existing `tools/*.yaml` with new tools |
| No matching toolset | **Build a new toolset** |

Show the user a short coverage table and get an explicit OK before building anything. **Do not scaffold the agent while toolsets are missing** — `get_toolset("...")` raises on unknown names.

To build or extend tools, follow the loop in [`docs/write-new-tool.md`](../../../docs/write-new-tool.md): explore the real schema with the `ibmi` CLI, draft and validate the SQL, author the YAML against [`docs/tool-design-reference.md`](../../../docs/tool-design-reference.md), then **always** regenerate:

```bash
uv run python parse_mcp_tools.py
```

The MCP server picks up YAML changes automatically (`YAML_AUTO_RELOAD=true`); the Python side reads `toolsets.json` for name resolution — both must be current.

## 3. Phase 2 — generate the agent file

Create `agents/<slug_underscore>_agent.py` mirroring [`agents/performance_agent.py`](../../../agents/performance_agent.py): module-level `AGENT_ID` / `NAME` / `DESCRIPTION`, an inline f-string `INSTRUCTIONS` with the agent's mission steps followed by the shared blocks, then tools and the instance:

```python
INSTRUCTIONS = f"""\
<the agent's mission and numbered working steps>

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
        include_tools=get_toolset("<toolset>"),
    ),
    *web_tools(),
]

<slug_underscore>_agent = Agent(
    id=AGENT_ID,
    name=NAME,
    model=AGENT_MODEL,
    description=DESCRIPTION,
    instructions=INSTRUCTIONS,
    tools=tools,
    markdown=True,
    add_datetime_to_context=True,
    db=get_postgres_db(),
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

Notes:

- `db=get_postgres_db()` (from `db`) — never construct a `PostgresDb` inline; the helper is memoized so every agent shares one instance.
- If the agent also uses a non-IBM i agno toolkit, ground it in the **`agno-docs` MCP** (configured in [`.mcp.json`](../../../.mcp.json)) before writing code — import path, constructor args, required env vars, pip deps. Never invent a toolkit.
- Db2 for i conventions the SQL side must respect are in `DATA_HANDLING`: `FETCH FIRST N ROWS ONLY` not `LIMIT`, `UPPER()` for case-insensitive comparisons, fully qualified `SCHEMA.TABLE` names.

## 4. Register in `app/main.py`

Add the import and append to the literal `agents=[…]` list — no registry, no autoloader:

```python
from agents.<slug_underscore>_agent import <slug_underscore>_agent
```

## 5. Manifest entry

Add the agent to [`app/config.yaml`](../../../app/config.yaml) under its `id`, following the existing entries: quick prompts that exercise the agent's real capabilities.

## 6. Restart the container

Uvicorn hot-reloads edits inside existing modules, but **registering a new agent module requires a restart**:

```bash
podman compose restart agentos-api
```

New pip deps instead? Add them to [`pyproject.toml`](../../../pyproject.toml), then `./scripts/generate_requirements.sh && podman compose up -d --build`.

Verify the agent registered before smoke-testing:

```bash
until curl -sSf http://localhost:8000/health > /dev/null; do sleep 0.5; done
curl -s http://localhost:8000/agents | jq -r '.[].id' | grep <slug>
```

## 7. Smoke test

Probe with **one of the quick prompts you wrote in Step 5** so the test exercises what real users will hit:

```bash
curl -sS -X POST http://localhost:8000/agents/<slug>/runs \
  -F "message=<one of the quick prompts>" \
  -F "user_id=claude-create-agent" \
  -F "stream=false" \
  -o /tmp/agent-out.json \
  -w "HTTP %{http_code} in %{time_total}s\n"

jq -r '.content // .' < /tmp/agent-out.json
```

Pass = `HTTP 200` and a non-empty `.content`. Check which tools fired (`AGNO_DEBUG=True` is set for dev in compose):

```bash
podman logs agentos-api --since 30s 2>&1 | grep -E "Running: \w+\(" | head -40
```

## 8. If the smoke test fails

- **HTTP 404** — not registered or not restarted. Re-check Steps 4 and 6. If both look right, `podman inspect agentos-api --format '{{ range .Mounts }}{{ .Source }} → {{ .Destination }}{{ "\n" }}{{ end }}'` to confirm `/app` is bound to *this* repo's path.
- **HTTP 5xx** — `podman logs agentos-api --tail 50` for the traceback. Most failures are import errors, an unknown toolset name, or a typo in `tools=`.
- **MCP tool errors** — check `podman logs ibmi-mcp-server --tail 50`: bad IBM i credentials, SQL errors against the live system, or a YAML that didn't reload.
- **Tool not firing when expected** — the instruction prompt isn't strong enough. Tighten, or run [`improve-agent`](../improve-agent/SKILL.md) once the agent is loaded.

Iterate at most 2-3 times before stopping and asking the user.

## 9. Done

Lead with the answer the agent just gave — that's their idea, alive, against their own system. Then the slug and where to reach it (the AgentOS UI at os.agno.com, or `http://localhost:8000` directly). Hand them the loop:

- [`/extend-agent`](../extend-agent/SKILL.md) — they drive: add a tool or capability, fix something it got wrong.
- [`/improve-agent`](../improve-agent/SKILL.md) — you drive: probe it against its own `INSTRUCTIONS` until it's reliable.
- [`/create-evals`](../create-evals/SKILL.md) — pin today's behavior down as tests. The smoke test that just passed is already a first case in the making; offer to persist it so the suite watches their agent from day one.
