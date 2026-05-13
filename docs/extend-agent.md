# Extend an IBM i Agent (add a new toolset)

> Claude Code prompt. Open Claude Code in this repo and paste:
> `Run docs/extend-agent.md`

You are pair-programming with the user to give an existing IBM i agent a new capability. Usually this means: add a new toolset (a `tools/*.yaml`), regenerate `tools/toolsets.json`, wire the toolset into the agent's `ibmi_tools([...])`, smoke-test.

Loop: change → smoke-test → "anything else?".

## 0. Preconditions

- Stack up: `curl -sSf http://localhost:8000/healthz` and `curl -sSf http://localhost:3010/healthz` both return 200.
- The user has named (a) the existing agent (slug) and (b) the capability they want to add.

If the capability isn't naturally an IBM i SQL/CL tool, route them to [`docs/create-new-agent.md`](create-new-agent.md) instead — they probably want a new agent rather than an extension.

## 1. Clarify the capability

Ask via `AskUserQuestion` in one message:

- **What does the new capability do?** One sentence. ("Show me the message queue contents", "List failed jobs from the last 24 hours", "Audit *PUBLIC authority on a library", …)
- **Does the data come from a known QSYS2 / SYSTOOLS view, a UDTF, or a CL command?** If they don't know, ask which approach feels closer; you can investigate.
- **Read-only or modifying?** Read-only is the default and safest. If modifying, the tool must be in `requires_confirmation` per `SQL_POLICY`.

## 2. Find or design the SQL / CL

Open the IBM i MCP server's tool YAMLs in `tools/` for reference. The schema is documented inline in `tools/sql-tools-config.schema.json`. The shape of a tool entry:

```yaml
sources:
  ibmi-system:
    host: ${DB2i_HOST}
    user: ${DB2i_USER}
    password: ${DB2i_PASS}
    port: ${DB2i_PORT:-8076}

tools:
  list_failed_jobs:
    source: ibmi-system
    title: List Failed Jobs
    description: |
      Returns jobs from the last N hours whose final status was *FAILED.
    statement: |
      SELECT job_name, job_user, job_status, message_text
      FROM TABLE(QSYS2.JOB_QUEUE_INFO())
      WHERE job_status = '*FAILED'
        AND start_timestamp > CURRENT TIMESTAMP - :hours_back HOURS
      FETCH FIRST :max_rows ROWS ONLY
    parameters:
      - name: hours_back
        type: integer
        default: 24
      - name: max_rows
        type: integer
        default: 100
    security:
      readOnly: true
    annotations:
      destructiveHint: false

toolsets:
  job_diagnostics:
    title: Job Diagnostics
    description: Diagnose failed and long-running jobs.
    tools:
      - list_failed_jobs
```

Rules:
- Use Db2 for i syntax (`FETCH FIRST`, parameter markers `:name`)
- Use fully qualified names (`QSYS2.JOB_QUEUE_INFO`, `SYSTOOLS.*`)
- Mark `readOnly: true` for SELECT-only tools — the MCP server's validator enforces this
- Group related tools into a `toolset` so agents can grab them as a unit

If the SQL is non-obvious, ask the user to confirm the QSYS2 / SYSTOOLS function or view name before pasting into the YAML.

## 3. Add the YAML

Create `tools/<new-toolset>.yaml`. Keep it focused — one toolset per file is the norm in this template.

## 4. Validate & regenerate

```bash
uv run python parse_mcp_tools.py
```

This validates every YAML against `tools/sql-tools-config.schema.json` and rewrites `tools/toolsets.json`. If validation fails, fix the YAML — schema errors print with line numbers.

## 5. Reload the MCP server

The compose file mounts `./tools` into the container with `YAML_AUTO_RELOAD=true`, so changes should pick up within a few seconds. Verify:

```bash
curl -s http://localhost:3010/mcp/tools | jq '.tools[].name' | grep <new-tool-name>
```

If the tool name doesn't appear, restart the container:

```bash
docker compose restart ibmi-mcp-server
```

## 6. Wire into the agent

Edit the agent module (`agents/<slug>.py`) and add the new toolset to its `ibmi_tools(...)` call:

```python
tools = collect_tools(
    ibmi_tools(
        [
            "<existing_toolset_a>",
            "<existing_toolset_b>",
            "<new_toolset>",            # added
        ],
        include_tools=CORE_SQL_TOOLS,
        requires_confirmation_tools=SQL_CONFIRMATION_TOOLS,
    ),
    _web,
)
```

If the new toolset has modifying tools, add their names to `requires_confirmation_tools` too.

Then update the agent's instruction markdown (`agents/instructions/ibmi-<slug>.md`) — add a routing rule that tells the agent **when** to use the new toolset. Without this, the agent will see new tools but not know when to pick them.

## 7. Restart and smoke test

```bash
docker compose restart agentos-api
sleep 2
uv run python cli.py --agent <slug> --prompt "<question only the new toolset can answer>"
```

Watch the response. Did the agent call the new tool? Was the output correct? If the agent ignored the new toolset, the instructions step (6) probably needs sharper routing language.

## 8. "Anything else?"

Ask the user if they want to add more tools to this toolset, or move on. Loop until done. Then summarize the changes (files touched, new toolset name, new tool names) and let the user commit.
