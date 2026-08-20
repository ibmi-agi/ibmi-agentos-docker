# Write a New Tool

> Field manual for the tool-authoring loop, used by the `create-agent` and `extend-agent` skills. Runnable standalone — open Claude Code in this repo and paste:
> `Run .agents/skills/create-agent/references/write-new-tool.md`

You are authoring a new SQL tool for this template. The end product is a `tools/*.yaml` entry that the `ibmi-mcp-server` publishes to the IBM i agents. The loop is: **explore with `ibmi` → draft SQL → write YAML → validate → verify live → commit**.

The `ibmi` CLI is the only database utility you use here. Background and command surface: [`docs/ibmi-cli.md`](../../../../docs/ibmi-cli.md). YAML schema reference: [`tool-design-reference.md`](tool-design-reference.md).

## 0. Preconditions

- `.env` populated. `DB2i_HOST` / `DB2i_USER` / `DB2i_PASS` set to a reachable IBM i with the `SAMPLE` library available.
- `ibmi` installed on the host (`ibmi --version`) — see [`docs/ibmi-cli.md`](../../../../docs/ibmi-cli.md) to install it. Sanity check returns today's date:

  ```bash
  ibmi sql "SELECT CURRENT_DATE FROM SYSIBM.SYSDUMMY1"
  ```

- Stack healthy:

  ```bash
  podman compose up -d --build
  until curl -sSf http://localhost:8000/healthz > /dev/null; do sleep 0.5; done
  curl -sSf http://localhost:3010/healthz
  ```

- YAML auto-reload on (default — confirm `YAML_AUTO_RELOAD=true` is set on the `ibmi-mcp-server` service in `compose.yaml`).

If any of these fail, stop and surface the issue before proceeding — there is no point writing a tool against a stack that can't load it.

## 1. Explore

Decide on the question the tool should answer. Drive the decision with the CLI — don't guess column names:

```bash
# What schemas does this system have?
ibmi schemas

# What lives in SAMPLE? (or your target schema)
ibmi tables SAMPLE

# Pick a table and capture its columns + types exactly
ibmi columns SAMPLE EMPLOYEE

# Need the DDL? Generate it
ibmi describe "SAMPLE.EMPLOYEE"
```

Aim for one of:

- A *single-row-or-small-set lookup* — e.g. "show me employee 000150."
- A *parameterized list* — e.g. "list employees in department :workdept."
- A *grouped aggregation* — e.g. "headcount by department."

Avoid kitchen-sink tools. The agent will route between several narrow tools much better than it composes one wide one.

## 2. Draft the SQL

Write the statement, paste it into `ibmi sql`, iterate until the output is what you want:

```bash
ibmi sql "
SELECT EMPNO, FIRSTNME, LASTNAME, SALARY
FROM SAMPLE.EMPLOYEE
WHERE WORKDEPT = 'A00'
ORDER BY EMPNO
FETCH FIRST 50 ROWS ONLY
"
```

IBM i SQL conventions apply (see [`tool-design-reference.md`](tool-design-reference.md) §7):

- `FETCH FIRST N ROWS ONLY` — never `LIMIT`.
- `UPPER(col) LIKE UPPER(:pattern)` for case-insensitive search on EBCDIC strings.
- Fully qualify every object: `SAMPLE.EMPLOYEE`, not `EMPLOYEE`.
- Job names in `number/user/name` form when you need them.

When the query is right, **parameterize what should be a tool parameter**. Use `:name` markers — they're what the YAML schema expects:

```bash
ibmi validate "
SELECT EMPNO, FIRSTNME, LASTNAME, SALARY
FROM SAMPLE.EMPLOYEE
WHERE WORKDEPT = :workdept
ORDER BY EMPNO
FETCH FIRST :row_limit ROWS ONLY
"
```

`ibmi validate` parses the statement and verifies every referenced object exists, without binding parameters. Loop on errors until it passes.

## 3. Write the YAML

Either extend the existing `tools/employee-info.yaml` (preferred when the new tool belongs alongside the SAMPLE tools) or create a new `tools/<name>.yaml` (one toolset per file is the convention).

Open [`tool-design-reference.md`](tool-design-reference.md) §2–§6 before authoring. Required shape:

```yaml
tools:
  list_employees_by_department:
    source: ibmi-sample
    description: |
      List employees in a specific department. Returns employee
      number, first name, last name, and salary. Use this when the
      user asks about a department by its 3-character code (e.g. 'A00').
    statement: |
      SELECT EMPNO, FIRSTNME, LASTNAME, SALARY
      FROM SAMPLE.EMPLOYEE
      WHERE WORKDEPT = :workdept
      ORDER BY EMPNO
      FETCH FIRST :row_limit ROWS ONLY
    parameters:
      - name: workdept
        type: string
        description: "3-character department code (e.g. 'A00')"
        required: true
      - name: row_limit
        type: integer
        description: "Maximum rows to return"
        default: 50
        min: 1
        max: 500
    security:
      readOnly: true
    annotations:
      readOnlyHint: true
      idempotentHint: true
      domain: "sample"
      category: "employees"
```

If you're creating a new toolset (a coherent group of tools the agent should grab as a unit), add a `toolsets:` block:

```yaml
toolsets:
  sample_data:
    title: "SAMPLE Data"
    description: "Schema discovery + employee data for the Db2 for i SAMPLE library."
    tools:
      - list_employees_by_department
      # ... other tool names in this toolset
```

If you're adding to an existing toolset, just append the new tool name to its `tools:` list.

Default to `security.readOnly: true`. Any tool that modifies state must set `readOnly: false`, pair it with `annotations.destructiveHint: true`, and be added to `requires_confirmation_tools` in the agent file — but that's a deliberate, rare decision.

## 4. Validate

Two steps — schema-validate the YAML, then regenerate the toolset index:

```bash
uv run python .agents/skills/create-agent/scripts/validate_tools.py tools/<file>.yaml
uv run python parse_mcp_tools.py
```

The first command downloads the authoritative schema fresh from the [ibmi-mcp-server repo](https://github.com/IBM/ibmi-mcp-server), validates your YAML against it in memory, and discards it — the schema is deliberately not stored in this repo, so it can never go stale. The second regenerates `tools/toolsets.json`. **A non-zero exit code means the YAML is broken** — fix and re-run. Read [`tool-design-reference.md`](tool-design-reference.md) §9 (common mistakes) and §10 (validation-error → fix map) before guessing.

The umbrella check (ruff + mypy + schema validation in one shot):

```bash
bash scripts/validate.sh
```

`scripts/validate.sh` is what CI runs; if it's green locally, it's green in CI.

## 5. Verify live

`ibmi-mcp-server` watches `tools/` and reloads on YAML changes (`YAML_AUTO_RELOAD=true`). Confirm the new tool is published:

```bash
curl -s http://localhost:3010/mcp/tools | jq '.tools[].name' | grep list_employees_by_department
```

If it isn't there, check the MCP server logs:

```bash
podman compose logs ibmi-mcp-server --tail 50
```

Then drive the tool from the agent — paste an example prompt that should route to it:

```bash
curl -sS -X POST http://localhost:8000/agents/ibmi-sample/runs \
  -F "message=List employees in department A00" \
  -F "user_id=claude-write-new-tool" \
  -F "stream=false" \
  -o /tmp/tool-out.json \
  -w "HTTP %{http_code} in %{time_total}s\n"

jq -r '.content // .' < /tmp/tool-out.json
```

Watch the container logs to confirm the new tool fired:

```bash
podman logs agentos-api --since 30s 2>&1 | grep -E "Running: \w+\(" | head -40
```

If the agent doesn't pick the new tool, the tool's `description:` text isn't routing the model well — sharpen the *when to use it* sentence. The agent reads `description`, not `name`.

## 6. Commit

Include the regenerated `tools/toolsets.json` in the commit — the Python side reads it to resolve toolset name → tool list.

```bash
git status     # tools/employee-info.yaml (or new file), tools/toolsets.json
git add tools/employee-info.yaml tools/toolsets.json
git commit -m "tools(employee-info): add list_employees_by_department"
```

That's the loop. Cycle back to step 1 for the next tool — narrow, one workflow at a time.
