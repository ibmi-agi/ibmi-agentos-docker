---
name: setup-platform
description: Set up this IBM i AgentOS from a fresh clone — confirm Podman and its compose provider (guiding the install if missing), configure .env (model key + IBM i credentials), create the project-scoped .ibmi/ config for the ibmi CLI, boot the three containers, verify they are healthy and hand the user the agent call that proves a real answer against their IBM i, connect the AgentOS UI, then hand over the agent-development loop. Use when the user asks to set up the platform, get started, or bring this repo up on a new machine.
---

# Set Up the Platform

> _**Coding-agent workflow** — a `/slash-command` your coding agent (Claude Code, Codex, others) runs while developing this repo. Invoke it by name (e.g. `/setup-platform`) or describe the task and it triggers automatically._

You are taking the user from a fresh clone to a running platform with a real agent answer from **their** IBM i system. The wow moment is Step 6 — one of the shipped agents reporting live system status from their machine, minutes after cloning. By default you hand the user that call to run themselves — it keeps them in the loop; they can ask you to run it instead. Everything before it is setup; everything after it is handing over the loop.

**Be self-driving:** anything you can do — open a file, open a URL, launch an app — do it. Stop when progress needs a human: typing a secret, installing software, a sign-in the flow can't continue without. When you do stop, tell the user exactly what to do. Never print or echo secret values.

**Narrate the trip:** open with a quick map of what's about to happen — tune the words, keep the shape — then a line as each step starts and a word when it lands:

```text
Kicking off /setup-platform. Here's the map for this trip:

1. Podman — confirm the runtime and its compose provider (guided install if missing)
2. Environment — .env: a model API key + your IBM i credentials
3. IBM i CLI — project-scoped `.ibmi/` config for the `ibmi` authoring tool
4. Boot — build and start the three platform containers
5. Prove it — a real agent answer from your IBM i (I'll hand you the command)
6. Connect the UI — os.agno.com, one click
7. Hand over the loop — the six shipped agents and how to build your own
```

## 1. Read the manual

Read [`AGENTS.md`](../../../AGENTS.md) end to end — it's the source of truth for how this platform works and answers most questions you'll hit along the way.

## 2. Podman

This skill's runtime is **Podman** (daemonless, no Docker Desktop). Two pieces have to check out:

- **The runtime**: `podman info` succeeds. On macOS and Windows, Podman runs containers in a VM — if `podman info` fails but `podman` exists, check `podman machine list`: no machine → `podman machine init`; a stopped machine → `podman machine start`, then poll `podman info` until it's up. On Linux there's no machine step.
- **The compose provider**: `podman compose version` succeeds, and `podman compose up --help` lists `--wait`. `podman compose` delegates to an external provider (`podman-compose`) — Podman alone isn't enough to bring the stack up — and the skills lean on `up --wait`: podman-compose **1.6.0+** or docker-compose v2 (podman-compose ≤ 1.5 lacks it: `brew upgrade podman-compose` / `pip install -U podman-compose`), on Podman ≥ 4.6.

**If Podman (or the compose provider) isn't installed, stop and hand the user the setup** — don't install it for them, and don't fall back to Docker:

- **macOS**:

  ```bash
  brew install podman podman-compose
  podman machine init
  podman machine start
  ```

- **Linux**: install both from the distro's package manager — `sudo apt install podman podman-compose` (Debian/Ubuntu) or `sudo dnf install podman podman-compose` (Fedora/RHEL). No machine step needed.
- **Windows**: install [Podman Desktop](https://podman-desktop.io) (or `winget install RedHat.Podman`), then `podman machine init` + `podman machine start`, and `pip install podman-compose` for the compose provider.

Wait for them to confirm, then re-run the checks (`podman info`, `podman compose version`, `podman compose up --help | grep -- --wait`) before moving on.

## 3. Environment

`.env` is the user's file — it holds their IBM i credentials and API keys, so they fill it in and its contents stay with them. Run `cp .env.example .env`, open it in their editor, and walk them through the two groups to fill in:

- **A model provider key** — agents default to `anthropic:claude-sonnet-4-5`, so `ANTHROPIC_API_KEY` is the one to set. If the user prefers another provider, set `AGENT_MODEL=<provider>:<model-id>` and the matching key instead (see the comments in [`.env.example`](../../../.env.example)).
- **IBM i credentials** — `DB2i_HOST`, `DB2i_USER`, `DB2i_PASS`. The `ibmi-mcp-server` container uses these to open Db2 for i connections; without them the agents have no system to talk to.

If a key is already set in their shell, say so — they can paste it in themselves. Open `.env` in their editor (cursor, code, etc.); never open a terminal editor like vim or nano from your own shell — it will hang the session. Bad values surface on their own: Step 4's `ibmi sql` check and Step 5's MCP-server healthcheck both fail on wrong IBM i credentials — point the user back to `.env` rather than inspecting it.

## 4. IBM i CLI — project-scoped

The `ibmi` CLI is the host-side authoring tool the agent-development loop leans on ([`docs/ibmi-cli.md`](../../../docs/ibmi-cli.md)). Set it up **project-scoped**: the CLI uses the nearest `.ibmi/config.yaml` (walking up from the working directory) and it overrides `~/.ibmi/config.yaml`, so a `.ibmi/` dir in this repo sandboxes every connection the user adds here — nothing leaks into, or reads from, their global config. The dir is git-ignored.

- **Install check**: `ibmi --version` (or `ibmi --help`). If missing, install it — `npm install -g @ibm/ibmi-cli` (Node 18+) — or note they can come back to this later: the platform runs without it; only tool authoring (`/create-agent`, `/extend-agent`) needs it.
- **Create the project config** — seeded with `${VAR}` references so the credentials live only in `.env`:

  ```bash
  mkdir -p .ibmi
  cat > .ibmi/config.yaml <<'EOF'
  # Project-scoped ibmi CLI connections — the nearest .ibmi/config.yaml wins
  # over ~/.ibmi/config.yaml, so systems added in this repo stay sandboxed
  # to it. ${VAR} references expand from the environment at load time.
  default: dev
  systems:
    dev:
      host: ${DB2i_HOST}
      user: ${DB2i_USER}
      password: ${DB2i_PASS}
  EOF
  ```

- **Verify** against their system:

  ```bash
  ibmi sql "SELECT CURRENT_DATE FROM SYSIBM.SYSDUMMY1"
  ```

  Today's date as a one-row table = the CLI and the platform now share one set of credentials. If it fails, the same `DB2i_*` values will also fail the MCP server in Step 5's boot — have the user fix them in `.env`, once.

Tell the user the sandbox rule in one line: any further system they add from inside this repo (`ibmi system add prod --host … --user …`) lands in the project's `.ibmi/config.yaml`, scoped to this project only.

## 5. Boot

Build the image, then start the platform and wait for it:

```bash
podman compose build            # the first build takes a few minutes
podman compose up -d --wait     # returns 0 once the stack is healthy
```

Three containers come up: `agentos-db` (Postgres + pgvector), `ibmi-mcp-server` (the IBM i tools server), and `agentos-api` (the agents). `--wait` blocks until `ibmi-mcp-server` and `agentos-api` pass the healthchecks declared in `compose.yaml`, and exits non-zero if either container exits or turns unhealthy. It is idempotent — re-run it if a tool call times out. Show the result:

```bash
podman ps --filter 'name=^(agentos-api|agentos-db|ibmi-mcp-server)$' --format '{{.Names}}\t{{.Status}}'
```

> **No host-side health polling — prefer podman-native commands.** Never `curl`/`nc` `localhost` in a loop to wait for the containers: on managed Windows laptops that pattern (powershell → curl.exe → localhost:8000 on a sleep cadence) matches an EDR beacon signature and has isolated a developer's machine. `--wait` and `podman healthcheck run` execute inside the podman VM; nothing on the host talks to localhost. See [`AGENTS.md`](../../../AGENTS.md) → *Verifying the stack*.

If `--wait` exits non-zero, read `podman compose logs agentos-api` / `podman compose logs ibmi-mcp-server` and fix what you find. The MCP server failing health is almost always the IBM i credentials in `.env`.

## 6. Prove it

Step 5's `--wait` already proved the stack healthy. Confirm the API once more, podman-natively, and say so:

```bash
podman healthcheck run agentos-api && podman healthcheck run ibmi-mcp-server && echo "API and MCP server healthy"
```

Then, by default, **hand the test to the user rather than running it yourself** — this is their moment, and seeing the answer arrive in their own terminal keeps them in the loop. Present this command; it asks the Performance Monitor for live system status (it reads `QSYS2` services that exist on every IBM i):

```bash
curl -sS -X POST http://localhost:8000/agents/ibmi-performance-monitor/runs \
  -F "message=What is the current system status? Check memory pools and CPU usage." \
  -F "user_id=setup-check" \
  -F "stream=false" \
  -o /tmp/setup-check.json \
  -w "HTTP %{http_code} in %{time_total}s\n"

jq -r '.content // .' < /tmp/setup-check.json
```

Tell them what to expect — a paragraph of memory-pool and CPU figures: that's their IBM i talking, through an agent they now own. If they'd rather you run it, run it and quote the answer. Either way, if it fails the usual suspects are the IBM i credentials in `.env` (`podman compose logs ibmi-mcp-server`) or the model key (`podman compose logs agentos-api`).

## 7. Connect the AgentOS UI

Their platform is live — show them how to connect the AgentOS UI, where they chat with agents and inspect sessions, memory, and traces. Render the connection details as a table:

| Setting | Value |
|---|---|
| AgentOS UI | https://os.agno.com |
| Connection type | **Local** |
| Endpoint | `http://localhost:8000` |
| Name | `IBM i AgentOS` (or their choice) |

Follow the table with one line of direction: https://os.agno.com, sign in, **Connect OS**, fill the form from the table. Don't gate on the click — roll straight into Step 8 while it connects; if they'd rather skip the UI, carry on.

## 8. Hand over the loop

Finish with a short summary: the six shipped agents (`ibmi-text2sql`, `ibmi-performance-monitor`, `ibmi-security-audit`, `ibmi-library-list-ops`, `ibmi-ptf-management`, `ibmi-sample` — one line each from [`app/config.yaml`](../../../app/config.yaml)), and the loop the user now owns:

- [`/create-agent`](../create-agent/SKILL.md) — build a new IBM i agent for their own domain: design the SQL toolset, scaffold the module, register it, prove it live.
- [`/extend-agent`](../extend-agent/SKILL.md) — they drive: give an existing agent a new tool or capability, refine its instructions, fix a known bug.
- [`/improve-agent`](../improve-agent/SKILL.md) — you drive: probe an agent against its own instructions, judge, edit, re-probe until it's reliable.

Mention in one line that the platform is also an MCP server at `http://localhost:8000/mcp` — this repo's `.mcp.json` already registers it for coding agents working in the checkout, and `claude mcp add --transport http agentos http://localhost:8000/mcp` registers it anywhere else.

Note the `ibmi-sample` agent expects the SAMPLE schema (`CALL QSYS.CREATE_SQL_SAMPLE('SAMPLE')` creates it) — mention it only if they ask about that agent.
