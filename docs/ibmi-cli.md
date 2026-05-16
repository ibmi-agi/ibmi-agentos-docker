# The `ibmi` CLI

> Operator reference. This is the single database utility you reach for when authoring or validating tools in this template — the `ibmi` command. Every other doc in this directory that touches Db2 for i refers back here.

Authoritative reference: <https://ibm-d95bab6e.mintlify.app/cli/overview.md>. Read it for the full command surface; this page covers the slice an agent author needs.

## What it is

`ibmi` is a small Node CLI that talks to a Mapepire daemon on an IBM i system. It reuses the exact same tool-logic functions the `ibmi-mcp-server` runs internally, so `ibmi schemas`, `ibmi tables SAMPLE`, and `ibmi sql "<stmt>"` return identical results to what the MCP server would publish to an agent.

That symmetry is the point. When you are authoring a `tools/*.yaml`, the CLI is how you:

1. Discover what exists in the target schema (`ibmi schemas`, `ibmi tables`, `ibmi columns`, `ibmi describe`).
2. Draft and validate the SQL the tool will run (`ibmi validate`, `ibmi sql`).
3. Dry-run a finished YAML tool the same way the MCP server would (`ibmi tool <name> --tools tools/<file>.yaml --dry-run`).

You commit the YAML only after the SQL works in the CLI. See [`docs/write-new-tool.md`](write-new-tool.md) for the end-to-end loop.

> **Not the same as `IBMI_CLI_MODE`.** [`docs/cli-mode.md`](cli-mode.md) describes a *runtime* toggle where agents call the bundled CLI binary instead of the MCP server. This doc is about using the CLI at *authoring time* to design tools, regardless of which runtime mode you deploy with.

## Already in the container

The Dockerfile's `node-builder` stage installs `@ibm/ibmi-cli` via npm and copies the binary + Node runtime into the Python runtime image. `ibmi` is on `PATH` inside `agentos-api` — you can shell in and use it without installing anything locally:

```bash
docker compose exec agentos-api ibmi --version
docker compose exec agentos-api ibmi schemas
```

Pin or bump the bundled CLI version at build time (default is `0.5.1`):

```bash
docker compose build --build-arg IBMI_CLI_VERSION=0.5.2 agentos-api
```

## Install locally (host)

For host-side authoring (faster iteration than `docker compose exec`):

```bash
npm install -g @ibm/ibmi-cli
ibmi --help
```

Requires Node.js 18+. If you don't want a global install, `npx -y @ibm/ibmi-mcp-server@latest ibmi --help` works too — the CLI ships inside the same npm package as the MCP server.

## Connecting — project-level config

The CLI walks up from your current working directory looking for the nearest `.ibmi/config.yaml`, the same way `git` walks up for `.git`. **For this template, put the config inside the repo so the CLI always uses the system you're authoring against — not whatever you happen to have set globally in `~/.ibmi/config.yaml`.**

`.ibmi/` is gitignored (see `.gitignore`); never commit it.

### One-shot setup

You already have `.env` with `DB2i_HOST` / `DB2i_USER` / `DB2i_PASS` — keep using it as the credential source and reference those values from the project config:

```bash
mkdir -p .ibmi
cat > .ibmi/config.yaml <<'YAML'
default: ibmi

systems:
  ibmi:
    host: ${DB2i_HOST}
    port: 8076
    user: ${DB2i_USER}
    password: ${DB2i_PASS}
    ignoreUnauthorized: true
    readOnly: true
YAML
```

`${VAR}` is expanded at load time from the environment, so load `.env` into your shell once per session (`set -a; source .env; set +a`) — or use [`direnv`](https://direnv.net/) so it happens automatically when you `cd` into the repo.

Sanity check:

```bash
ibmi sql "VALUES CURRENT_DATE"
```

You should see today's date printed as a one-row table.

### Multiple systems

Add more entries under `systems:` (dev / prod / lpar-a / lpar-b …) and pick one with `--system`, `IBMI_SYSTEM=...`, or the `default:` key. The `ibmi system add` subcommand will write the entry for you and also append `.ibmi/` to `.gitignore` if it isn't already there:

```bash
ibmi system add dev  --host dev.ibmi.example.com  --user MYUSER     # prompts for password
ibmi system add prod --host prod.ibmi.example.com --user MYUSER
ibmi system default dev
ibmi system test --all
ibmi system list
```

### Zero-config fallback

If you skip the project config entirely, the CLI falls back to the `DB2i_HOST` / `DB2i_USER` / `DB2i_PASS` / `DB2i_PORT` env vars from your shell. That works, but you lose per-project options (`readOnly`, `defaultSchema`, `maxRows`, named systems) — prefer the project config.

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
ibmi tool list_employees --workdept A00 --tools tools/sample.yaml --dry-run
```

Full command reference: <https://ibm-d95bab6e.mintlify.app/cli/commands.md>.

## Next

- [`docs/write-new-tool.md`](write-new-tool.md) — the full explore → draft → write → validate → commit loop.
- [`docs/tool-design-reference.md`](tool-design-reference.md) — the YAML schema you'll be writing against.
- [`docs/extend-knowledge.md`](extend-knowledge.md) — using the CLI to capture column metadata for a knowledge-base entry.
