---
name: setup-platform
description: Set up this IBM i AgentOS from a fresh clone — confirm Docker, configure .env (model key + IBM i credentials), boot the three containers, prove a real agent answer against the user's IBM i, connect the AgentOS UI, then hand over the agent-development loop. Use when the user asks to set up the platform, get started, or bring this repo up on a new machine.
---

# Set Up the Platform

> _**Coding-agent workflow** — a `/slash-command` your coding agent (Claude Code, Codex, others) runs while developing this repo. Invoke it by name (e.g. `/setup-platform`) or describe the task and it triggers automatically._

You are taking the user from a fresh clone to a running platform with a real agent answer from **their** IBM i system. The wow moment is Step 5 — one of the shipped agents reporting live system status from their machine, minutes after cloning. Everything before it is setup; everything after it is handing over the loop.

**Be self-driving:** anything you can do — open a file, open a URL, launch an app — do it. Stop when progress needs a human: typing a secret, installing software, a sign-in the flow can't continue without. When you do stop, tell the user exactly what to do. Never print or echo secret values.

**Narrate the trip:** open with a quick map of what's about to happen — tune the words, keep the shape — then a line as each step starts and a word when it lands:

```text
Kicking off /setup-platform. Here's the map for this trip:

1. Docker — confirm it's installed and running
2. Environment — .env: a model API key + your IBM i credentials
3. Boot — build and start the three platform containers
4. Prove it — a real agent answer from your IBM i
5. Connect the UI — os.agno.com, one click
6. Hand over the loop — the six shipped agents and how to build your own
```

## 1. Read the manual

Read [`AGENTS.md`](../../../AGENTS.md) end to end — it's the source of truth for how this platform works and answers most questions you'll hit along the way.

## 2. Docker

Confirm Docker is installed and running (`docker info` succeeds). If it's installed but not running, start it (`open -a Docker` on macOS) and poll until it's up. Stop for the user only if Docker isn't installed — give them the steps to install Docker Desktop and wait.

## 3. Environment

Run `cp .env.example .env`, then help the user fill in two groups:

- **A model provider key** — agents default to `anthropic:claude-sonnet-4-5`, so `ANTHROPIC_API_KEY` is the one to set. If the user prefers another provider, set `AGENT_MODEL=<provider>:<model-id>` and the matching key instead (see the comments in [`.env.example`](../../../.env.example)).
- **IBM i credentials** — `DB2i_HOST`, `DB2i_USER`, `DB2i_PASS`. The `ibmi-mcp-server` container uses these to open Db2 for i connections; without them the agents have no system to talk to.

If a key is already set in their shell, say you found one and offer to copy it in — move the value across without reading or printing it. Otherwise open `.env` in their editor (cursor, code, etc.) and ask them to paste values in. Never open a terminal editor like vim or nano from your own shell — it will hang the session.

## 4. Boot

Start the platform with `docker compose up -d --build`. Three containers come up: `agentos-db` (Postgres + pgvector), `ibmi-mcp-server` (the IBM i tools server), and `agentos-api` (the agents). Poll until both health probes pass (the first build takes a few minutes):

```bash
curl -sSf http://localhost:8000/health     # AgentOS API
curl -sSf http://localhost:3010/healthz    # IBM i MCP server
```

If either never comes up, read `docker compose logs agentos-api` / `docker compose logs ibmi-mcp-server` and fix what you find. The MCP server failing health is almost always the IBM i credentials in `.env`.

## 5. Prove it

Ask the Performance Monitor for live system status — it reads `QSYS2` services that exist on every IBM i, so it works regardless of what's installed:

```bash
curl -sS -X POST http://localhost:8000/agents/ibmi-performance-monitor/runs \
  -F "message=What is the current system status? Check memory pools and CPU usage." \
  -F "user_id=setup-check" \
  -F "stream=false" \
  -o /tmp/setup-check.json \
  -w "HTTP %{http_code} in %{time_total}s\n"

jq -r '.content // .' < /tmp/setup-check.json
```

Quote the answer to the user — that's their IBM i talking, through an agent they now own.

## 6. Connect the AgentOS UI

Their platform is live — show them how to connect the AgentOS UI, where they chat with agents and inspect sessions, memory, and traces. Render the connection details as a table:

| Setting | Value |
|---|---|
| AgentOS UI | https://os.agno.com |
| Connection type | **Local** |
| Endpoint | `http://localhost:8000` |
| Name | `IBM i AgentOS` (or their choice) |

Follow the table with one line of direction: https://os.agno.com, sign in, **Connect OS**, fill the form from the table. Don't gate on the click — roll straight into Step 7 while it connects; if they'd rather skip the UI, carry on.

## 7. Hand over the loop

Finish with a short summary: the six shipped agents (`ibmi-text2sql`, `ibmi-performance-monitor`, `ibmi-security-audit`, `ibmi-library-list-ops`, `ibmi-ptf-management`, `ibmi-sample` — one line each from [`app/config.yaml`](../../../app/config.yaml)), and the loop the user now owns:

- [`/create-agent`](../create-agent/SKILL.md) — build a new IBM i agent for their own domain: design the SQL toolset, scaffold the module, register it, prove it live.
- [`/extend-agent`](../extend-agent/SKILL.md) — they drive: give an existing agent a new tool or capability, refine its instructions, fix a known bug.
- [`/improve-agent`](../improve-agent/SKILL.md) — you drive: probe an agent against its own instructions, judge, edit, re-probe until it's reliable.

Note the `ibmi-sample` agent expects the SAMPLE schema (`CALL QSYS.CREATE_SQL_SAMPLE('SAMPLE')` creates it) — mention it only if they ask about that agent.
