# Tool Design Reference

> Companion to [`write-new-tool.md`](write-new-tool.md), [`docs/extend-agent.md`](../../../../docs/extend-agent.md), and [`docs/create-new-agent.md`](../../../../docs/create-new-agent.md). Read this **before** authoring a new `tools/*.yaml` — it's the schema, the conventions, and the pitfalls in one place.

This doc covers **authoring**. For the architectural picture (how MCP server, YAMLs, and `parse_mcp_tools.py` fit together), see [`docs/ibmi-mcp-server.md`](../../../../docs/ibmi-mcp-server.md).

## 1. YAML top-level shape

```yaml
sources:    # connection definitions (usually one: ibmi-system)
tools:      # tool definitions (dict, keyed by tool name)
toolsets:   # toolset definitions (dict, keyed by toolset name)
metadata:   # optional global metadata
```

The authoritative schema is [`sql-tools-config.json` in the ibmi-mcp-server repo](https://raw.githubusercontent.com/IBM/ibmi-mcp-server/refs/heads/main/packages/server/src/ibmi-mcp-server/schemas/json/sql-tools-config.json) — the validation script ([`../scripts/validate_tools.py`](../scripts/validate_tools.py)) downloads it fresh on every run, so it's never stored (or stale) in this repo. Schema is `additionalProperties: false` at every level — **unknown keys fail validation**. Read the live schema before adding anything novel.

### Sources

One source per repo. The template's default is `ibmi-sample`, parameterized from env vars. Every tool references this source.

```yaml
sources:
  ibmi-sample:
    host: ${DB2i_HOST}
    user: ${DB2i_USER}
    password: ${DB2i_PASS}
    port: 8076                  # Mapepire default
    ignore-unauthorized: true   # accept self-signed certs
```

You usually don't redefine `sources:` in new YAMLs — declare it once (in `tools/employee-info.yaml`) and reference it from any additional `tools/*.yaml` files by name.

## 2. Tool fields

Each entry under `tools:` is a tool. Keys:

| Field | Required | Purpose |
|---|---|---|
| `source` | ✅ | Source name (`ibmi-system`) |
| `description` | ✅ | What the tool does + when to use it. AI-facing — write it for the agent, not the user |
| `statement` | (effectively) | SQL with `:param` placeholders |
| `parameters` | optional | Array of parameter defs (see §3) |
| `security` | optional | `readOnly`, `maxQueryLength`, `forbiddenKeywords` |
| `annotations` | optional | UI/client hints (see §4) |
| `domain` | optional | Top-level domain tag (e.g. `operations`, `sysadmin`) |
| `category` | optional | Top-level category tag (e.g. `daily_health`, `discovery`) |
| `metadata` | optional | Free-form dict — `title:` is the common key |
| `responseFormat` | optional | `json` (default) or `markdown` |
| `tableFormat` | optional | `markdown`, `ascii`, `grid`, `compact` |
| `maxDisplayRows` | optional | Truncate result display (default 100, max 1000) |
| `enabled` | optional | Default `true` — set `false` to skip publishing |

Deprecated (don't use): top-level `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint` — put these under `annotations:` instead.

## 3. Parameter shape

`parameters:` is a **YAML list** (not a dict). Each item:

| Field | Required | Notes |
|---|---|---|
| `name` | ✅ | Matches `:name` in `statement` |
| `type` | ✅ | One of: `string`, `boolean`, `integer`, `float`, `array` (all lowercase) |
| `description` | recommended | Human-readable — shows up in MCP tool schema |
| `default` | optional | Used if caller omits the param |
| `required` | optional | Boolean. Overrides `default` semantics |
| `itemType` | array only | `string` / `boolean` / `integer` / `float` |
| `min` / `max` | numeric only | Range checks |
| `minLength` / `maxLength` | string/array only | Length checks |
| `enum` | optional | Allowed values |
| `pattern` | string only | Regex |

Worked example:

```yaml
parameters:
  - name: workdept
    type: string
    description: "3-character department code (e.g. 'A00') from SAMPLE.DEPARTMENT"
    required: true
  - name: row_limit
    type: integer
    description: "Maximum rows to return"
    default: 50
    min: 1
    max: 500
```

## 4. Security & annotations

### `security` block

```yaml
security:
  readOnly: true              # default: true. Server validator rejects writes if true
  maxQueryLength: 10000       # optional
  forbiddenKeywords: [DROP]   # optional — additional to the default forbidden list
```

If your tool modifies state (UPDATE, DELETE, INSERT, certain CL UDTFs), set `readOnly: false` **and** add `annotations.destructiveHint: true`. The Python side will then need this tool listed in `requires_confirmation_tools` when wiring into an agent.

### `annotations` block

UI/client hints — also surface in MCP tool metadata:

```yaml
annotations:
  readOnlyHint: true          # mirror of security.readOnly
  idempotentHint: true        # same input → same output
  destructiveHint: false      # pair with readOnly: false when true
  openWorldHint: false        # talks to external/unpredictable systems
  domain: "sample"            # client-side filtering
  category: "employees"       # client-side filtering
  toolsets: ["sample_data"]   # optional explicit toolset list
```

Convention in this template: SELECT-only tools always set `readOnlyHint: true` and `idempotentHint: true`.

## 5. Toolsets

Toolsets group tools so agents can grab them as a unit (`MCPTools(... include_tools=get_toolset("sample_data"))`).

```yaml
toolsets:
  sample_data:
    title: "SAMPLE Data"
    description: "Schema discovery + employee data for the Db2 for i SAMPLE library."
    tools:
      - list_sample_tables
      - describe_sample_table
      - list_employees_by_department
```

Required: `tools:` (non-empty list). A tool can belong to multiple toolsets — just list it in each.

Conventions:
- **One toolset per file.** `tools/<toolset>.yaml`. Mirrors the in-repo example (`tools/employee-info.yaml`).
- **Keep toolsets cohesive.** A toolset is a *workflow* — "SAMPLE data", "security audit". Not a category dump.
- **Names are kebab/snake_case.** File: `employee-info.yaml` or `daily-health.yaml`. Toolset key: `sample_data` or `daily_health`. Pick one; we use snake for the key, kebab for the filename.
- **Don't over-group.** If three tools serve very different intents, split into two toolsets.

## 6. Worked examples

### Example A — Simple parameterized SELECT

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

### Example B — Discovery tool against a catalog view

```yaml
tools:
  describe_sample_table:
    source: ibmi-sample
    description: |
      Return column metadata (name, type, length, nullable) for a
      table in the SAMPLE library. Use this when you need to confirm
      the shape of a SAMPLE.* table before composing SQL against it.
    statement: |
      SELECT COLUMN_NAME, DATA_TYPE, LENGTH,
             IS_NULLABLE, COLUMN_DEFAULT
      FROM QSYS2.SYSCOLUMNS
      WHERE TABLE_SCHEMA = 'SAMPLE'
        AND TABLE_NAME = :table_name
      ORDER BY ORDINAL_POSITION
    parameters:
      - name: table_name
        type: string
        required: true
        description: "Table name within SAMPLE (case-sensitive, uppercase)"
    security:
      readOnly: true
    annotations:
      readOnlyHint: true
      idempotentHint: true
      domain: "sample"
      category: "discovery"

toolsets:
  sample_data:
    title: "SAMPLE Data"
    description: "Schema discovery + employee data for the Db2 for i SAMPLE library."
    tools:
      - describe_sample_table
      - list_employees_by_department
```

## 7. IBM i SQL conventions (non-negotiable)

These come from `agents/utils/common.py::DOMAIN_RULES` and apply to every tool YAML:

- **Db2 for i syntax**: `FETCH FIRST N ROWS ONLY` — **never** `LIMIT`
- **EBCDIC strings**: `UPPER(col) LIKE UPPER(:pattern)` for case-insensitive comparisons
- **Fully qualified names**: `SAMPLE.EMPLOYEE`, `QSYS2.SYSCOLUMNS`. Never bare names — library list is unreliable in MCP context
- **Parameter markers**: `:param_name` (positional `?` works too but `:` is the convention)
- **Job names**: `number/user/name` format (e.g. `123456/QSYS/QPADEV0001`)
- **Authority levels**: `*USE`, `*CHANGE`, `*ALL`, `*EXCLUDE`, `*PUBLIC`

## 8. CL / PASE commands

The YAML schema is **SQL-only**. There is no top-level "command" tool type — every YAML tool runs a SQL `statement`.

To run CL or PASE commands from an agent, the agent uses the MCP server's **built-in** `execute_cl_command` / `execute_pase_command` tools (already in the runtime, not authored in YAML). Wire them via `include_tools=[...]` and **always** mark them in `requires_confirmation_tools`. If you need a CL invocation wrapped as a YAML tool, do it through `QCMDEXC`:

```yaml
statement: |
  CALL QSYS2.QCMDEXC(:cl_command)
```

This goes through the same SQL path. Mark `readOnly: false` + `destructiveHint: true` unless you can prove the wrapped command is safe.

## 9. Common mistakes

Curated from real validator failures and the live schema:

| Mistake | Why it fails | Fix |
|---|---|---|
| `parameters:` as a dict (`param_name: {type: string}`) | Schema requires `array` | Use `- name: param_name\n  type: string` |
| `type: Integer` or `type: number` | Enum is lowercase: `string`/`boolean`/`integer`/`float`/`array` | `type: integer` |
| `${param_name}` in `statement` | Env var syntax — params use `:` | `:param_name` |
| `LIMIT 50` in `statement` | Db2 for i doesn't support `LIMIT` | `FETCH FIRST 50 ROWS ONLY` |
| Bare table name `EMPLOYEE` | Library list isn't reliable | `SAMPLE.EMPLOYEE` |
| Tool listed as `- tool_name` under `tools:` (top-level) | `tools:` is a dict (`tool_name:`) — list form is for toolsets | `tool_name:` as a key |
| Setting both `readOnly: true` and `destructiveHint: true` | Contradictory | Pick one: read-only or destructive |
| Top-level `readOnlyHint:` on the tool | Deprecated — schema validates but emits warnings | Move under `annotations:` |
| Forgetting `source:` on a tool | `source` is required | Add `source: ibmi-system` |
| `minimum:` / `maximum:` on parameter | Schema uses `min` / `max` (no -imum) | `min: 1`, `max: 500` |
| Adding an unknown key (e.g. `examples:`) | Schema is `additionalProperties: false` | Drop the key, or fold into `description` |
| Toolset with empty `tools: []` | Schema requires `minItems: 1` | Add at least one tool |

## 10. Validation-error → fix map

When `uv run python .agents/skills/create-agent/scripts/validate_tools.py tools/<file>.yaml` fails, the error format is roughly:

```
✗ tools/<file>.yaml — N error(s)
    at <json-path>: <jsonschema error>
```

Common error → fix:

| Error fragment | Meaning | Fix |
|---|---|---|
| `'parameters' is not of type 'array'` | You wrote a dict | Convert to list of `- name: …` items |
| `'<type>' is not one of ['string', 'boolean', 'integer', 'float', 'array']` | Wrong case or wrong value | Use lowercase enum value |
| `Additional properties are not allowed ('<key>' was unexpected)` | Unknown key | Remove the key or move under the right block (`annotations:` / `metadata:`) |
| `'source' is a required property` | Missing `source:` | Add `source: ibmi-system` |
| `'tools' is a required property` | Empty toolset | Add at least one tool name |
| `is too short` on `tools` array under toolsets | `tools: []` | Add at least one entry |
| `'name' is a required property` (parameters) | Param missing `name:` | Add it |

On any failure: **re-read this doc** (especially §2, §3, §9) before editing the YAML. Most failures map to one of the common mistakes above.

## 11. Tool design heuristics

When deciding *what* tools to build:

- **Narrow scope beats kitchen sink.** Five focused tools an agent can route between beat one `run_any_sql` tool that the agent has to compose every time.
- **Parameterize what varies.** If two intents differ only by a `WHERE` clause value, that's one parameterized tool, not two.
- **Validate at the SQL layer.** Use `enum` on parameters whose values are a fixed set (status codes, message types). Use `min`/`max` on row limits.
- **AI-facing descriptions.** The `description:` is read by the agent. Tell it *when* to use the tool, *what* it returns, and *how it differs* from sibling tools. See `tools/employee-info.yaml` for good examples.
- **Default to read-only.** Make a deliberate decision to allow writes; never default to it.
- **One toolset, one workflow.** A toolset is the unit of agent capability — design it as a coherent set of operations the agent will use together.

## 12. Authoring loop

The recommended order — see [`write-new-tool.md`](write-new-tool.md) for the full operator-prompt version:

1. **Explore** — `ibmi schemas`, `ibmi tables SAMPLE`, `ibmi columns SAMPLE EMPLOYEE` to capture real column names/types
2. **Draft the SQL** — write the statement against the explored schema
3. **Validate the SQL** — `ibmi validate "<your statement>"` (or `ibmi sql "<stmt>"` to run a small slice). Loop on errors
4. **Author YAML** — against this doc's §2–§5
5. **Validate YAML** — `uv run python .agents/skills/create-agent/scripts/validate_tools.py tools/<file>.yaml` (downloads the live schema, validates, discards). Loop using §10
6. **Regenerate the index** — `uv run python parse_mcp_tools.py` rewrites `tools/toolsets.json`
7. **Verify in MCP** — `curl -s http://localhost:3010/mcp/tools | jq '.tools[].name' | grep <your_tool>`

The `ibmi` CLI is the only database utility in this loop — see [`docs/ibmi-cli.md`](../../../../docs/ibmi-cli.md) for the command surface.

---

## Validate before commit

Every new or edited YAML must pass schema validation before it lands on `main`. Two entry points:

```bash
uv run python .agents/skills/create-agent/scripts/validate_tools.py tools/   # live-schema validation (download → validate → discard)
uv run python parse_mcp_tools.py                                             # regenerates tools/toolsets.json
bash scripts/validate.sh                                                     # umbrella: ruff + mypy + schema validation + index regen
```

`scripts/validate.sh` is what CI runs; if it's green locally, it's green in CI. A non-zero exit means fix and re-run — re-read §9 and §10 above before editing the YAML, since most failures map to a known mistake.

Always commit the regenerated `tools/toolsets.json` alongside the YAML it was generated from — the Python side reads `toolsets.json` to resolve toolset names. Full authoring loop with worked SAMPLE examples: [`write-new-tool.md`](write-new-tool.md).
