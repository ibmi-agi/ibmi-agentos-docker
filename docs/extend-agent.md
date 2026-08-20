# Extend an IBM i Agent (build a new tool / toolset)

> Claude Code prompt. Open Claude Code in this repo and paste:
> `Run docs/extend-agent.md`

You are pair-programming with the user to give an existing IBM i agent a new capability. That means: design one or more SQL tools, write them as a new `tools/*.yaml`, regenerate `tools/toolsets.json`, wire the toolset into the agent's `MCPTools(... include_tools=get_toolset("..."))`, smoke-test.

The schema, conventions, and pitfalls live in **[`tool-design-reference.md`](../.agents/skills/create-agent/references/tool-design-reference.md)** — read it before authoring YAML. The end-to-end tool-authoring loop with worked SAMPLE examples lives in **[`write-new-tool.md`](../.agents/skills/create-agent/references/write-new-tool.md)**. CLI background: [`docs/ibmi-cli.md`](ibmi-cli.md). This doc orchestrates the iterative agent-extension flow; those are the field manuals.

Loop: clarify → introspect → validate SQL → preview → author YAML → smoke-test → "anything else?".

## 0. Preconditions

- Stack up: `curl -sSf http://localhost:8000/healthz` and `curl -sSf http://localhost:3010/healthz` both return 200.
- The user has named (a) the existing agent (slug — the SAMPLE Data Agent is `ibmi-sample`) and (b) the capability they want to add.
- `ibmi` CLI working: `ibmi sql "SELECT CURRENT_DATE FROM SYSIBM.SYSDUMMY1"` returns today's date. Used for introspection and SQL validation. Setup: [`docs/ibmi-cli.md`](ibmi-cli.md).

If the capability isn't naturally an IBM i SQL tool (e.g. it's a new agent persona, or it's purely CL with no SQL surface), route the user to [`docs/create-new-agent.md`](create-new-agent.md) instead.

## 1. Clarify the capability

Ask via `AskUserQuestion` in **one** consolidated message:

- **What does the new capability do?** One sentence. ("Audit *PUBLIC authority on user profiles", "List failed jobs from the last 24 hours", "Show storage usage per ASP", …)
- **Where does the data live?** A known `QSYS2` / `SYSTOOLS` view? A UDTF? Unknown — investigate by introspection? Pick one.
- **Read-only or modifying?** Read-only is the default and the safest. If modifying, the tool will need `readOnly: false` + `destructiveHint: true` and must be added to `requires_confirmation_tools` in the agent.
- **Domain / category** — short tags for `annotations.domain` / `annotations.category` (e.g. `operations` / `daily_health`, `security` / `audit`). Surface existing tag values from `tools/*.yaml` so the user can match.

Don't proceed until you have these answers.

## 2. Introspect IBM i

Before writing SQL, capture the real schema. Pick the level of detail that matches what the user said in step 1.

```bash
# Find the schema/library
ibmi schemas --filter "SAMPLE"

# Find candidate tables/views in a schema
ibmi tables SAMPLE

# Get exact column names and types
ibmi columns SAMPLE EMPLOYEE

# Or generate DDL for a deeper look
ibmi describe "SAMPLE.EMPLOYEE"
```

If the user named a UDTF/view, jump straight to `ibmi columns` / `ibmi describe`. If they're not sure, browse with `ibmi tables`. Capture the **exact** column names and types — Db2 for i is case-sensitive about identifier quoting and Tech Refresh adds/removes columns regularly.

## 3. Draft and validate the SQL

Write the SQL statement (or statements — one per tool you plan to ship). Apply [`tool-design-reference.md`](../.agents/skills/create-agent/references/tool-design-reference.md) §7 conventions: `FETCH FIRST`, `UPPER()` for EBCDIC, fully qualified names, `:param` placeholders.

Validate every statement before adding it to YAML:

```bash
ibmi validate "SELECT EMPNO, FIRSTNME, LASTNAME, SALARY
FROM SAMPLE.EMPLOYEE
WHERE WORKDEPT = :workdept
FETCH FIRST 50 ROWS ONLY"
```

Parameter markers (`:name`) are fine in `ibmi validate` — it parses without binding. Loop on syntax errors. For a quick reality check, run a small slice:

```bash
ibmi sql "SELECT COUNT(*) FROM SAMPLE.EMPLOYEE"
```

Don't move forward until every planned statement passes validation.

## 4. Preview the tool plan with the user

Before writing any YAML, show the user a markdown table of what you intend to ship:

```markdown
| Tool name | Description | SQL (preview) | Parameters | Read-only |
|---|---|---|---|---|
| list_employees_by_department | Lists employees in a given department | SELECT … FROM SAMPLE.EMPLOYEE WHERE WORKDEPT = :workdept | workdept (string, required), row_limit (int, default 50) | yes |
| count_employees_by_job | Aggregates headcount per JOB code | SELECT JOB, COUNT(*) FROM SAMPLE.EMPLOYEE GROUP BY JOB | (none) | yes |
```

Then ask: **"Confirm this plan or request changes?"** Wait for an explicit OK.

This is the equivalent of ixora's `agent_builder.py` "preview-before-register" gate. Don't skip it — it's much cheaper to revise the plan now than to rewrite YAML + re-run `parse_mcp_tools.py` twice.

## 5. Author the YAML

Read [`tool-design-reference.md`](../.agents/skills/create-agent/references/tool-design-reference.md) §2–§6 before authoring. Then create `tools/<new-toolset>.yaml` (or extend `tools/employee-info.yaml` if the new tool naturally fits the SAMPLE toolset). **One toolset per file** is the convention.

Skeleton (fill in from your plan + introspection):

```yaml
# Optional: redeclare sources only if this file is standalone.
# Otherwise rely on sources declared in another tools/*.yaml (e.g. employee-info.yaml).

tools:
  <tool_name>:
    source: ibmi-sample
    description: |
      <AI-facing description: what it returns, when to use it,
       how it differs from sibling tools>
    statement: |
      SELECT ...
      FROM QSYS2.<view_or_udtf>
      WHERE ...
      FETCH FIRST :row_limit ROWS ONLY
    parameters:
      - name: <param>
        type: <string|integer|boolean|float|array>
        description: "..."
        required: true
    security:
      readOnly: true
    annotations:
      readOnlyHint: true
      idempotentHint: true
      domain: "<domain>"
      category: "<category>"

toolsets:
  <toolset_name>:
    title: "<Human title>"
    description: "<one-line summary>"
    tools:
      - <tool_name>
```

For modifying tools (`readOnly: false`), add `destructiveHint: true` under `annotations`, and remember step 7 will plumb the tool into `requires_confirmation_tools`.

## 6. Validate and regenerate

```bash
uv run python .agents/skills/create-agent/scripts/validate_tools.py tools/<file>.yaml
uv run python parse_mcp_tools.py
```

The first command validates the YAML against the live ibmi-mcp-server schema (downloaded fresh on every run, then discarded — never stored in this repo); the second rewrites `tools/toolsets.json`. If validation fails:

1. Read the error path and message.
2. Consult [`tool-design-reference.md`](../.agents/skills/create-agent/references/tool-design-reference.md) §9 (common mistakes) and §10 (validation-error → fix map).
3. Fix the YAML, rerun. (Exit code 2 means the schema download itself failed — check the network before blaming the YAML.)

Don't skip rereading the reference — most errors map directly to a known mistake.

## 7. Verify the MCP server picked it up

The compose file mounts `./tools` into the MCP container with `YAML_AUTO_RELOAD=true`, so changes should appear within a few seconds:

```bash
curl -s http://localhost:3010/mcp/tools | jq '.tools[].name' | grep <new-tool-name>
```

If the tool doesn't appear:

```bash
podman compose logs ibmi-mcp-server --tail 50    # check for reload errors
podman compose restart ibmi-mcp-server           # nuclear option
```

## 8. Wire into the agent

Edit the agent module (`agents/<slug>.py`) and add the new toolset to its `MCPTools(...)` call. To combine the new toolset with the agent's existing one, swap `get_toolset("...")` for `get_toolsets("...", "...")` (both from `agents.utils.tools`):

```python
from agents.utils.tools import get_toolsets

tools = [
    MCPTools(
        url=MCP_URL,
        transport="streamable-http",
        timeout_seconds=30,
        include_tools=get_toolsets(
            "<existing_toolset>",
            "<new_toolset>",                       # added
        ),
        # If any tool in the new toolset is modifying (readOnly: false):
        # requires_confirmation_tools=["<modifying_tool>"],
    ),
    *web_tools(),
]
```

If any tool in the new toolset is modifying (`readOnly: false`), add its name to `requires_confirmation_tools` too.

Then update the agent's inline `INSTRUCTIONS` f-string in `agents/<slug>.py` — add a routing rule that tells the agent **when** to reach for the new toolset. Without this, the agent will see new tools but not know when to pick them.

## 9. Restart and smoke test

```bash
podman compose restart agentos-api
sleep 2
curl -sS -X POST http://localhost:8000/agents/ibmi-<slug>/runs \
  -F message='<question only the new toolset can answer>'
```

Watch the response. Did the agent call the new tool? Was the output correct? If the agent ignored the new toolset, sharpen the routing language in the inline `INSTRUCTIONS` (step 8) and try again.

## 10. "Anything else?"

Ask the user if they want to add more tools to this toolset, or move on. Loop until done. Then summarize the changes (files touched, new toolset name, new tool names) and let the user commit — don't run `git add` automatically.
