# The `ibmi` CLI

> Operator reference. This is the single database utility you reach for when authoring or validating tools in this template — the `ibmi` command. Every other doc in this directory that touches Db2 for i refers back here.

Authoritative reference: <https://ibm-d95bab6e.mintlify.app/cli/overview.md>. Read it for the full command surface; this page covers the slice an agent author needs.

## What it is

`ibmi` is a small Node CLI that talks to a Mapepire daemon on an IBM i system. It reuses the exact same tool-logic functions the `ibmi-mcp-server` runs internally, so `ibmi schemas`, `ibmi tables SAMPLE`, and `ibmi sql "<stmt>"` return identical results to what the MCP server would publish to an agent.

That symmetry is the point. When you are authoring a `tools/*.yaml`, the CLI is how you:

1. Discover what exists in the target schema (`ibmi schemas`, `ibmi tables`, `ibmi columns`, `ibmi describe`).
2. Draft and validate the SQL the tool will run (`ibmi validate`, `ibmi sql`).
3. Dry-run a finished YAML tool the same way the MCP server would (`ibmi tool <name> --tools tools/<file>.yaml --dry-run`).

You commit the YAML only after the SQL works in the CLI. See [`write-new-tool.md`](../.agents/skills/create-agent/references/write-new-tool.md) for the end-to-end loop.

## Install it

`ibmi` is a host-side authoring tool — install it once on your machine:

```bash
npm install -g @ibm/ibmi-cli
ibmi --help
```

Requires Node.js 18+. If you don't want a global install, `npx -y @ibm/ibmi-mcp-server@latest ibmi --help` works too — the CLI ships inside the same npm package as the MCP server.

## Connecting — `.env` is enough

If your `.env` already has the values the MCP server uses, the CLI picks them up automatically — no extra config needed:

| Env var       | Used as                                  |
| ------------- | ---------------------------------------- |
| `DB2i_HOST`   | IBM i hostname or IP                     |
| `DB2i_USER`   | IBM i user profile                       |
| `DB2i_PASS`   | Password for that profile                |
| `DB2i_PORT`   | Mapepire port — defaults to `8076`        |

Sanity check from the host (with `.env` loaded into the shell, or after `set -a; source .env; set +a`):

```bash
ibmi sql "SELECT CURRENT_DATE FROM SYSIBM.SYSDUMMY1"
```

You should see today's date printed as a one-row table.

For multiple systems (dev / prod / lpar-a / lpar-b …), use named connections — they live in `.ibmi/config.yaml` and take priority over the `DB2i_*` env vars. The CLI reads the **nearest `.ibmi/config.yaml`** walking up from the working directory, and it overrides the user-level `~/.ibmi/config.yaml` — so this template keeps a **project-scoped `.ibmi/` at the repo root** (git-ignored; `/setup-platform` seeds it with a `dev` system whose fields are `${DB2i_*}` references into `.env`). Systems you add from inside the repo land there, sandboxed to this project:

```bash
ibmi system add dev --host dev.ibmi.example.com --user MYUSER     # prompts for password
ibmi system add prod --host prod.ibmi.example.com --user MYUSER
ibmi system default dev
ibmi system test --all
ibmi system list
```

## The minimum command set for tool authoring

These four are the ones you'll use in every authoring loop:

```bash
# 1. What schemas exist?
ibmi schemas

# 2. What tables are in the schema I care about?
ibmi tables SAMPLE

# 3. What columns does this table have?
ibmi columns SAMPLE EMPLOYEE

# 4. Run / draft the SQL the tool will execute
ibmi sql "SELECT EMPNO, FIRSTNME, LASTNAME FROM SAMPLE.EMPLOYEE FETCH FIRST 5 ROWS ONLY"
```

Two more come up often once the YAML exists:

```bash
# Verify the statement parses and every object exists — without executing
ibmi validate "SELECT * FROM SAMPLE.EMPLOYEE WHERE WORKDEPT = :workdept"

# Dry-run a YAML tool exactly as the MCP server would resolve it
ibmi tool find_employees_by_department --department_id A00 --tools tools/employee-info.yaml --dry-run
```

Full command reference: <https://ibm-d95bab6e.mintlify.app/cli/commands.md>.

## Next

- [`write-new-tool.md`](../.agents/skills/create-agent/references/write-new-tool.md) — the full explore → draft → write → validate → commit loop.
- [`tool-design-reference.md`](../.agents/skills/create-agent/references/tool-design-reference.md) — the YAML schema you'll be writing against.
