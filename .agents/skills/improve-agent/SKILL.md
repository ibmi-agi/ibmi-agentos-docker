---
name: improve-agent
description: Autonomous hardening loop for an existing IBM i agent — derive probes from the agent's INSTRUCTIONS and from its real usage recorded in the database, run them against the live container, judge responses, edit the agent file, and re-probe until it reliably does what its instructions say. No user input needed. Use to harden an agent against its stated intent; to make a concrete change instead, use extend-agent.
---

# Improve an Agent

> _**Coding-agent workflow** — a `/slash-command` your coding agent (Claude Code, Codex, others) runs while developing this repo. Invoke it by name (e.g. `/improve-agent`) or describe the task and it triggers automatically._

You are recursively improving a target agent **autonomously**. **No user-supplied test cases** — you derive probes from the agent's stated purpose (its `INSTRUCTIONS`) and from its recorded usage (real sessions in the database, when the platform has any), test the agent against them, judge the results, and iterate on the agent file until it reliably does what its instructions say. The usage half is what makes this loop **reflective self-improvement**: reflect on how the agent is actually used, then improve it accordingly.

This is the autonomous half of the iteration loop. The user-driven half lives in [`extend-agent`](../extend-agent/SKILL.md). Use that skill to *change* the agent; use this one to *harden* it.

This is a **single-pass** loop — one pass usually takes 15-30 minutes. Re-run if behavior still drifts.

**Probes run real SQL against the configured IBM i system.** The shipped toolsets are read-only, so probing is safe by construction — but confirm the posture in Step 1, and keep probe volume reasonable: this is someone's live system, not a fixture.

## 0. Preconditions

- Stack up: `podman healthcheck run agentos-api && podman healthcheck run ibmi-mcp-server` exits 0. If not, ask the user to `podman compose up -d --build --wait` first.
- Live container is bound to *this* checkout:

  ```bash
  podman inspect agentos-api --format '{{range .Mounts}}{{.Source}}{{"\n"}}{{end}}' | grep -F "$(pwd)"
  ```

  Empty result = bound to a different repo path; fix before editing anything.
- Ask the user for the target agent **slug** (e.g. `ibmi-security-audit`) if they haven't named one.
- Recommend a feature branch (`git checkout -b improve/<slug>-$(date +%Y%m%d)`).

## 1. Read the agent's intent

Open `agents/<slug_underscore>_agent.py`. Capture:

- **Stated purpose** — docstring, `DESCRIPTION`, and the mission steps in `INSTRUCTIONS`.
- **Toolsets** — which `get_toolset("...")` names are wired; open [`tools/toolsets.json`](../../../tools/toolsets.json) for the member tools and check their read-only posture.
- **Explicit rules** — the shared blocks (`GUARDRAILS`, `DATA_HANDLING`, `ERROR_HANDLING`, `AUDIT`, `WEB`, `USER_CONTEXT`) promise concrete behaviors: redaction, confirmation before destructive ops, prompt-injection defense, error narration, action logging. These are all probe material.
- **Confirmation gates** — anything in `requires_confirmation_tools` (e.g. `execute_sql` on `ibmi-text2sql`).

Restate the agent's purpose in 1-2 sentences before generating probes. If the user has specific failure modes in mind, fold them in — otherwise you're flying solo.

## 2. Derive probes

Probes come from two sources: what the agent *promises* (`INSTRUCTIONS`) and what it actually *faces* (recorded usage). Mine the record first — a real ask is the strongest probe there is, because it will come back.

**Mine usage.** The platform records sessions in Postgres (needs the repo venv — `./scripts/venv_setup.sh` once, then `source .venv/bin/activate`; the compose defaults reach the local DB):

```python
from db import get_postgres_db
db = get_postgres_db()
# deserialize=False keeps the (rows, total) tuple shape and returns plain dicts
sessions, _ = db.get_sessions(component_id="<slug>", limit=20, deserialize=False)
asks = [run["input"]["input_content"] for s in sessions for run in (s.get("runs") or []) if run.get("input")]
```

Skim the asks for **recurring shapes** (the golden path as users actually phrase it), **visible fumbles** (wrong tool, fabrication, wrong format — a recorded response is a *scenario*, never the oracle; expected behavior still comes from `INSTRUCTIONS`), and **out-of-scope asks** (things users want that `INSTRUCTIONS` never promised — probe how gracefully the agent declines, and surface the gap in Step 8 as an [`extend-agent`](../extend-agent/SKILL.md) candidate). Reword anything that names real systems, schemas, or people before it becomes a probe. A fresh platform with no sessions is fine: instruction-derived probes are the floor, mining only adds.

**Derive from `INSTRUCTIONS`.** Aim for 2-3 probes per distinct rule plus 1-2 adversarial ones — most agents here land at 8-12, across four categories:

- **Golden path** (3-5): typical, in-scope questions. For IBM i agents, questions answerable from `QSYS2` services the toolset actually covers.
- **Edge cases** (2-3): ambiguous, out-of-scope, or boundary questions — a schema that doesn't exist, a service the toolset doesn't wrap. The agent should admit ignorance, refuse, or ask — not fabricate.
- **Tool selection** (2-3): questions designed to test that the *right* tool fires (and the wrong one doesn't) — e.g. a question the toolset answers directly vs. one that should route to `query_web`.
- **Adversarial** (1-2): prompt injection embedded in the question (`GUARDRAILS` promises defense), or a request to bypass a confirmation gate.

For each probe, write a one-line **expected behavior** drawn from the agent's `INSTRUCTIONS`. *You* are the oracle. Judge against what the instructions promise, not your own taste — a behavior you want that isn't promised is a Step 5 "add a rule" edit, not a probe failure.

## 3. Run the probes against the live agent

Tag each probe with a unique `user_id` so log lines can be correlated:

```bash
curl -sS -X POST http://localhost:8000/agents/<slug>/runs \
  -F "message=<probe text>" \
  -F "user_id=probe-<n>" \
  -F "stream=false" \
  -o /tmp/probe-<n>.json \
  -w "HTTP %{http_code} in %{time_total}s\n"

jq -r '.content // .' < /tmp/probe-<n>.json
```

Read the tool calls (`AGNO_DEBUG=True` in dev compose):

```bash
podman logs agentos-api --since 30s 2>&1 | grep -E "Running: \w+\(" | head -40
```

Logs are container-global — with parallel probes, filter by `user_id` instead. SQL-side failures surface in `podman logs ibmi-mcp-server`. Save each response so you can compare before vs. after.

## 4. Judge each probe

Tag each **PASS** / **FAIL**. Group failures by likely root cause:

- **Missing rule** — `INSTRUCTIONS` don't push for the behavior you expected.
- **Wrong tool selection** — wrong tool fired, or the agent stopped after one call when it should have drilled deeper.
- **Hallucination** — fabricated data when a query failed or the toolset doesn't cover the question. `ERROR_HANDLING` explicitly forbids this — a strong FAIL.
- **Injection / scope** — the agent let content in the question override its role. `GUARDRAILS` promises defense; a slip is a FAIL with an instructions-shaped fix.
- **Wrong format / tone** — answer right, shape off.
- **Environment failure** — bad IBM i credentials, rate limit, MCP server unreachable, missing schema on the target system (e.g. SAMPLE not installed for `ibmi-sample`). Surface to the user; don't paper over — and don't "fix" the agent for an environment problem.
- **Paused for confirmation** — a probe that reaches a `requires_confirmation_tools` member (e.g. `execute_sql` on `ibmi-text2sql`) returns `"status": "PAUSED"` with empty content. That is *correct* HITL behavior, not a failure — judge whether pausing was the right call, not the empty text.

## 5. Edit

Apply surgical edits. One lever per iteration:

- **Instructions** — most fixes live here. Edit the agent's own mission section in `agents/<slug_underscore>_agent.py`. Touch the shared blocks in [`agents/utils/common.py`](../../../agents/utils/common.py) only when the fix genuinely belongs to **every** agent — a common.py edit changes all six.
- **Toolset composition** — add a toolset the agent needs, or narrow `include_tools` if a tool is being misused. New SQL tools go through the [`extend-agent`](../extend-agent/SKILL.md) authoring path (`ibmi` CLI → YAML → `uv run python parse_mcp_tools.py`).
- **Confirmation gates** — add a misfiring modifying tool to `requires_confirmation_tools`.
- **`num_history_runs`** — raise if the agent loses context across turns; lower if old turns leak into new ones.
- **Model** — `AGENT_MODEL` in `.env` is a global switch; a per-agent override in the file is the last resort.

Keep edits short — more than ~5 new instruction lines in one pass means you're bolting; back up and reword instead.

## 6. Restart, re-probe failing cases

```bash
podman compose up -d --force-recreate --no-deps --wait agentos-api
podman exec agentos-api grep -c "<unique substring from your edit>" /app/agents/<slug_underscore>_agent.py
```

`0` = the edit didn't reach the container (bind-mount mismatch — Step 0 catches this earlier). Re-run **only the probes that failed**, plus a spot-check on 1-2 previously-passing probes to catch regressions.

## 7. Iterate

Cap at **5 iterations**. Stop when all probes pass; when the same probe fails 3 iterations in a row on the same lever (likely not prompt-shaped — a toolset gap, a model limit, or missing data on the target system; surface it, don't grind); or when 5 iterations elapse.

## 8. Report

- N probes generated, M passed initially, K passed finally.
- One line per accepted edit (which lever, what changed).
- Out-of-scope asks surfaced by mining — each an [`extend-agent`](../extend-agent/SKILL.md) candidate.
- `git diff agents/<slug_underscore>_agent.py` (one short block).
- Suggested commit message (`fix(<slug>): <one-line summary>`) and next step.

If a probe caught a real issue, don't let it evaporate — offer to graduate it into a
`Case` in [`evals/cases.py`](../../../evals/cases.py) via
[`create-evals`](../create-evals/SKILL.md) (which carries the case-writing rules:
read-only inputs, toolset-grounded assertions, value-free rubrics), so the regression
you just fixed stays fixed. Probes mined from real sessions are the strongest
candidates: that ask has already happened once.
