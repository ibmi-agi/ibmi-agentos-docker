# Tool Design Reference

> Companion to `docs/extend-agent.md` and `docs/create-new-agent.md`. Read this **before** authoring a new `tools/*.yaml` — it's the schema, the conventions, and the pitfalls in one place.

This doc covers **authoring**. For the architectural picture (how MCP server, YAMLs, and `parse_mcp_tools.py` fit together), see [`docs/ibmi-mcp-server.md`](ibmi-mcp-server.md).

## 1. YAML top-level shape

```yaml
sources:    # connection definitions (usually one: ibmi-system)
tools:      # tool definitions (dict, keyed by tool name)
toolsets:   # toolset definitions (dict, keyed by toolset name)
metadata:   # optional global metadata
```

The authoritative schema is `tools/sql-tools-config.schema.json`. Schema is `additionalProperties: false` at every level — **unknown keys fail validation**. Read the live schema before adding anything novel.

### Sources

One source per repo. The template's default is `ibmi-system`, parameterized from env vars. Every tool references this source.

```yaml
sources:
  ibmi-system:
    host: ${DB2i_HOST}
    user: ${DB2i_USER}
    password: ${DB2i_PASS}
    port: 8076                  # Mapepire default
    ignore-unauthorized: true   # accept self-signed certs
```

You usually don't redefine `sources:` in new YAMLs — declare it once (e.g. in `daily-health.yaml`) and reference it from elsewhere. Some files (e.g. `sys-admin.yaml`) leave `sources:` commented out and rely on it being declared in a sibling file.

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
  - name: job_name
    type: string
    description: "Qualified job name (e.g., '123456/MYUSER/MYJOB') or '*' for the current job"
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
  domain: "operations"        # client-side filtering
  category: "daily_health"    # client-side filtering
  toolsets: ["daily_health"]  # optional explicit toolset list
```

Convention in this template: SELECT-only tools always set `readOnlyHint: true` and `idempotentHint: true`.

## 5. Toolsets

Toolsets group tools so agents can grab them as a unit (`ibmi_tools(["daily_health"])`).

```yaml
toolsets:
  daily_health:
    title: "Daily Health Check Tools"
    description: "Job log and system value tools for daily IBM i health monitoring."
    tools:
      - joblog_info
      - system_value_lookup
```

Required: `tools:` (non-empty list). A tool can belong to multiple toolsets — just list it in each.

Conventions:
- **One toolset per file.** `tools/<toolset>.yaml`. Mirrors the in-repo examples.
- **Keep toolsets cohesive.** A toolset is a *workflow* — "daily health check", "service discovery". Not a category dump.
- **Names are kebab/snake_case.** File: `daily-health.yaml`. Toolset key: `daily_health`. Pick one; we use snake for the key, kebab for the filename.
- **Don't over-group.** If three tools serve very different intents, split into two toolsets.

## 6. Worked examples

### Example A — Simple parameterized SELECT

```yaml
tools:
  system_value_lookup:
    source: ibmi-system
    description: |
      Find system configuration values by name pattern using LIKE
      syntax (use % as wildcard). Returns numeric and character values.
      Useful patterns: '%SEC%' for security, '%LOG%' for logging.
    statement: |
      SELECT SYSTEM_VALUE_NAME,
             CURRENT_NUMERIC_VALUE,
             CURRENT_CHARACTER_VALUE
      FROM QSYS2.SYSTEM_VALUE_INFO
      WHERE UPPER(SYSTEM_VALUE_NAME) LIKE UPPER(:name_pattern)
      ORDER BY SYSTEM_VALUE_NAME
      FETCH FIRST 100 ROWS ONLY
    parameters:
      - name: name_pattern
        type: string
        description: "Pattern to match system value names (e.g., '%LMT%', '%SEC%')"
        required: true
    security:
      readOnly: true
    annotations:
      readOnlyHint: true
      idempotentHint: true
      domain: "operations"
      category: "daily_health"
```

### Example B — UDTF with multiple parameters + enum

```yaml
tools:
  joblog_info:
    source: ibmi-system
    description: |
      Retrieve job log messages. Use job_name '*' for the current job;
      otherwise pass a qualified name (number/user/name). Filter by
      message_type_filter: 'ESCAPE' for errors, 'DIAGNOSTIC' for warnings.
    statement: |
      SELECT MESSAGE_TIMESTAMP, MESSAGE_ID, MESSAGE_TYPE,
             SEVERITY, MESSAGE_TEXT
      FROM TABLE(QSYS2.JOBLOG_INFO(:job_name))
      WHERE (:message_type_filter = '*ALL'
             OR MESSAGE_TYPE = :message_type_filter)
      ORDER BY ORDINAL_POSITION DESC
      FETCH FIRST :row_limit ROWS ONLY
    parameters:
      - name: job_name
        type: string
        required: true
        description: "Qualified job name or '*' for current job"
      - name: message_type_filter
        type: string
        default: "*ALL"
        enum: ["*ALL", "ESCAPE", "DIAGNOSTIC", "INFORMATIONAL", "COMPLETION", "NOTIFY"]
        description: "Filter by message type"
      - name: row_limit
        type: integer
        default: 50
        min: 1
        max: 200
        description: "Maximum number of messages to return"
    security:
      readOnly: true
    annotations:
      readOnlyHint: true
      idempotentHint: true
      domain: "operations"
      category: "daily_health"

toolsets:
  daily_health:
    title: "Daily Health Check Tools"
    description: "Job log and system value tools for daily IBM i health monitoring."
    tools:
      - joblog_info
      - system_value_lookup
```

## 7. IBM i SQL conventions (non-negotiable)

These come from `agents/utils/common.py::DOMAIN_RULES` and apply to every tool YAML:

- **Db2 for i syntax**: `FETCH FIRST N ROWS ONLY` — **never** `LIMIT`
- **EBCDIC strings**: `UPPER(col) LIKE UPPER(:pattern)` for case-insensitive comparisons
- **Fully qualified names**: `QSYS2.ACTIVE_JOB_INFO`, `SYSTOOLS.WHOAMI`. Never bare names — library list is unreliable in MCP context
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
| Bare table name `ACTIVE_JOB_INFO` | Library list isn't reliable | `QSYS2.ACTIVE_JOB_INFO` |
| Tool listed as `- tool_name` under `tools:` (top-level) | `tools:` is a dict (`tool_name:`) — list form is for toolsets | `tool_name:` as a key |
| Setting both `readOnly: true` and `destructiveHint: true` | Contradictory | Pick one: read-only or destructive |
| Top-level `readOnlyHint:` on the tool | Deprecated — schema validates but emits warnings | Move under `annotations:` |
| Forgetting `source:` on a tool | `source` is required | Add `source: ibmi-system` |
| `minimum:` / `maximum:` on parameter | Schema uses `min` / `max` (no -imum) | `min: 1`, `max: 500` |
| Adding an unknown key (e.g. `examples:`) | Schema is `additionalProperties: false` | Drop the key, or fold into `description` |
| Toolset with empty `tools: []` | Schema requires `minItems: 1` | Add at least one tool |

## 10. Validation-error → fix map

When `uv run python parse_mcp_tools.py` fails, the error format is roughly:

```
✗ tools/<file>.yaml: <jsonschema error>
  at <json-pointer-path>
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
- **AI-facing descriptions.** The `description:` is read by the agent. Tell it *when* to use the tool, *what* it returns, and *how it differs* from sibling tools. See `tools/sys-admin.yaml` for good examples.
- **Default to read-only.** Make a deliberate decision to allow writes; never default to it.
- **One toolset, one workflow.** A toolset is the unit of agent capability — design it as a coherent set of operations the agent will use together.

## 12. Authoring loop

The recommended order, modeled on the workflow in `docs/extend-agent.md`:

1. **Introspect** — `ibmi schemas`, `ibmi tables QSYS2`, `ibmi columns QSYS2 ACTIVE_JOB_INFO` to capture real column names/types
2. **Draft the SQL** — write the statement against the introspected schema
3. **Validate the SQL** — `ibmi validate "<your statement>"` (or `ibmi sql --raw "<stmt>"` to run a small slice). Loop on errors
4. **Author YAML** — against this doc's §2–§5
5. **Validate YAML** — `uv run python parse_mcp_tools.py`. Loop using §10
6. **Verify in MCP** — `curl -s http://localhost:3010/mcp/tools | jq '.tools[].name' | grep <your_tool>`

That's the same shape ixora's `agent_builder.py` follows internally — introspect, validate SQL, read schema, write YAML, validate YAML. The Claude Code equivalent runs each step through `ibmi` / `uv` / `curl` via Bash.
