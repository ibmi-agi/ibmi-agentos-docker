---
name: extend-agent
description: User-driven loop to change an existing IBM i agent — add a SQL tool/toolset (ibmi CLI introspection, YAML authoring), add an agno toolkit or capability, refine its instructions, or fix a specific known bug, verifying each change against the live container. Use whenever the user names a concrete change to an agent. For autonomous hardening with no specific change in mind, use improve-agent.
---

# Extend an Agent

> _**Coding-agent workflow** — a `/slash-command` your coding agent (Claude Code, Codex, others) runs while developing this repo. Invoke it by name (e.g. `/extend-agent`) or describe the task and it triggers automatically._

You are recursively extending a target agent **with the user in the driver's seat**. Each iteration: the user names a change, you implement it (using the `ibmi` CLI for IBM i tool work and the `agno-docs` MCP for agno research), the change is verified against the live agent, then you ask if there's more to do. Stop when the user says they're done.

This is the user-driven half of the iteration loop. The autonomous half lives in [`improve-agent`](../improve-agent/SKILL.md) — probes derived from the agent's `INSTRUCTIONS` and recorded usage, no user input. Use this skill to *change* the agent; run that one afterward to confirm nothing regressed.

## 0. Preconditions

- Stack up: `curl -sSf http://localhost:8000/health` and `curl -sSf http://localhost:3010/healthz` both return 200. If not, ask the user to `docker compose up -d --build` first.
- Live container is bound to *this* checkout — otherwise restarts won't pick up your edits:

  ```bash
  docker inspect agentos-api --format '{{range .Mounts}}{{.Source}}{{"\n"}}{{end}}' | grep -F "$(pwd)"
  ```

  Empty result = the container's `/app` is bound to a different repo path. Either `cd` there or restart the stack from this directory.
- Ask the user for the target agent **slug** (e.g. `ibmi-performance-monitor`) if they haven't named one.
- For IBM i tool work: `ibmi sql "VALUES CURRENT_DATE"` returns today's date ([`docs/ibmi-cli.md`](../../../docs/ibmi-cli.md)).
- Recommend a feature branch (`git checkout -b extend/<slug>-$(date +%Y%m%d)`) so wrong turns are easy to revert.

## 1. Read the agent first

Open `agents/<slug_underscore>_agent.py`. Capture:

- **Stated purpose** — the docstring, `DESCRIPTION`, and `INSTRUCTIONS`.
- **Toolsets** — which `get_toolset("...")` names are wired; open [`tools/toolsets.json`](../../../tools/toolsets.json) to see the member tools.
- **Shared blocks** — which of `common.py`'s blocks its `INSTRUCTIONS` interpolate.
- **Safety posture** — anything in `requires_confirmation_tools`; whether its toolsets are read-only.

Restate the agent's purpose to the user in 1-2 sentences before asking what to change. This catches "I thought it did X but actually it does Y" upfront.

## 2. Ask what to improve

Use the coding agent's structured user-input control when available, else concise plain text. Multi-select is fine — handle changes sequentially, one per loop iteration:

- **Add an IBM i tool / toolset** — a new SQL capability against the user's system. The main path here.
- **Add an agno toolkit or capability** — a non-IBM i toolkit, memory tweak, knowledge base.
- **Refine instructions** — clarify a rule, narrow scope, change tone or format.
- **Fix a bug** — a specific failing prompt or wrong behavior.
- **Something else** — free-form.

For "Fix a bug" or "Something else," follow up for specifics (the failing prompt, observed vs. wanted behavior).

## 3. Ground the change

- **Add an IBM i tool / toolset** — follow the authoring loop in [`docs/write-new-tool.md`](../../../docs/write-new-tool.md): introspect the real schema with the `ibmi` CLI (`ibmi schemas`, `ibmi tables`, `ibmi describe`), draft and `ibmi validate` the SQL, author the YAML per [`docs/tool-design-reference.md`](../../../docs/tool-design-reference.md), then **always** `uv run python parse_mcp_tools.py` to regenerate `toolsets.json`. Wire the toolset into the agent's `MCPTools(... include_tools=get_toolset("..."))`. Read-only by default; a modifying tool needs `readOnly: false` + `destructiveHint: true` in YAML **and** membership in the agent's `requires_confirmation_tools`.
- **Add an agno toolkit / capability** — search the **`agno-docs` MCP** (configured in [`.mcp.json`](../../../.mcp.json)) before writing code; capture import path, constructor args, env vars, pip deps. Fall back to <https://docs.agno.com/llms.txt> only if the MCP is unavailable.
- **Refine instructions** — no docs needed. Propose a minimal diff. Edit the agent's own mission section; touch the shared blocks in [`agents/utils/common.py`](../../../agents/utils/common.py) only if the rule really belongs to **every** agent — a common.py edit changes all six.
- **Fix a bug** — reproduce the failure on the live agent first (Step 5's curl), then identify the layer: `INSTRUCTIONS` (most common), toolset (wrong or missing tool), the tool's SQL itself (test it with `ibmi sql`), model, or env (rate limit, missing key, MCP server unreachable).

## 4. Propose, then edit

Before editing, tell the user in 2-3 lines what you're about to change and why. Get a quick "yes" — most missteps come from misunderstanding the ask, not bad code.

Files in scope: `agents/<slug_underscore>_agent.py`, [`tools/*.yaml`](../../../tools/) (+ regenerated `toolsets.json`), [`app/main.py`](../../../app/main.py) (only for registration changes), [`app/config.yaml`](../../../app/config.yaml) (refresh quick prompts to exercise the new capability), [`pyproject.toml`](../../../pyproject.toml) (only for new pip deps).

Keep edits surgical — one change per iteration so each can be smoke-tested independently.

## 5. Restart

```bash
docker compose restart agentos-api
```

New pip deps: `./scripts/generate_requirements.sh && docker compose up -d --build` instead. Tool YAML changes alone don't need a restart — the MCP server auto-reloads them — but the restart is still the deterministic option when `toolsets.json` changed.

Poll `/health` until the API is back, then confirm the edit reached the container:

```bash
until curl -sSf http://localhost:8000/health > /dev/null; do sleep 0.5; done
docker exec agentos-api grep -c "<unique substring from your edit>" /app/agents/<slug_underscore>_agent.py
```

`0` means the file in the container hasn't changed — almost always the bind-mount mismatch Step 0 catches.

## 6. Smoke test the change

Pick a prompt that **exercises the change you just made**. For a new tool, it should force that tool to fire; for a bug fix, reuse the failing prompt; for an instruction refinement, a prompt the rule was meant to handle.

```bash
curl -sS -X POST http://localhost:8000/agents/<slug>/runs \
  -F "message=<the targeted prompt>" \
  -F "user_id=claude-extend-agent" \
  -F "stream=false" \
  -o /tmp/extend-out.json \
  -w "HTTP %{http_code} in %{time_total}s\n"

jq -r '.content // .' < /tmp/extend-out.json
```

Read tool calls from the logs (`AGNO_DEBUG=True` in dev compose):

```bash
docker logs agentos-api --since 30s 2>&1 | grep -E "Running: \w+\(" | head -40
```

A probe that reaches a `requires_confirmation_tools` member comes back `"status": "PAUSED"` with empty content — that's correct HITL behavior, not a failure; judge whether pausing was right.

Show the user the response and the tool calls. Did the change land?

- **Yes** — Step 7.
- **Almost** — one more edit pass. Cap at 2-3 iterations before asking how to proceed.
- **No / made it worse** — surface what happened. Offer to revert only your last patch after showing `git diff`; don't discard unrelated user edits.

## 7. Loop or wrap up

Ask: *"Anything else to improve, or are we done?"* More → Step 2. Done → Step 8.

## 8. Report

- One line per accepted change (which lever, what changed).
- `git diff --stat` plus a short `git diff` block for the agent file.
- Suggested commit message — `feat(<slug>): …` for new tools/capabilities, `fix(<slug>): …` for bug fixes, `chore(<slug>): refine instructions` for prompt-only edits.
- **Recommended next step** — run [`improve-agent`](../improve-agent/SKILL.md) to verify the agent still does what its `INSTRUCTIONS` say; the change just widened its surface area.
