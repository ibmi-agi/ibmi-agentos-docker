---
name: eval-and-improve
description: Run the eval suite (python -m evals), diagnose every failure, fix what's in scope, and loop until all cases pass. Use when evals are failing or when the user wants to run, diagnose, or repair the eval suite. To author new coverage, use create-evals instead.
---

# Eval and Improve

> _**Coding-agent workflow** — a `/slash-command` your coding agent (Claude Code, Codex, others) runs while developing this repo. Invoke it by name (e.g. `/eval-and-improve`) or describe the task and it triggers automatically._

You're running the platform's eval suite, diagnosing every failure, fixing what's in scope, and stopping when all cases pass. The eval wiring lives in [`evals/cases.py`](../../../evals/cases.py) (declares `agno.eval.Case`s) and [`evals/__main__.py`](../../../evals/__main__.py) (a thin entrypoint over agno's eval suite runner), while fixes may also touch `agents/<slug>_agent.py` or — this template's specialty — the SQL inside [`tools/*.yaml`](../../../tools/) per Step 3. Each case uses agno's built-in [`AgentAsJudgeEval`](https://docs.agno.com/evals/agent-as-judge) (LLM judge against a `criteria` rubric, binary pass/fail) and/or [`ReliabilityEval`](https://docs.agno.com/evals/reliability) (asserts which tools fired) — no custom DSL.

One thing to hold the whole time: **every case runs real (read-only) SQL against the IBM i system configured in `.env`.** A red suite can mean a broken agent, a broken case, a broken tool, or a system that simply doesn't have the data — diagnosis is deciding which.

## 0. Preconditions

- Postgres reachable on 5432: `nc -z localhost 5432` returns 0. If not, `podman compose up -d agentos-db`.
- MCP server live: `curl -sSf http://localhost:3010/healthz` returns 200. If not, `podman compose up -d ibmi-mcp-server`. Cases import the agents in-process — no AgentOS API server needed — but their tools call the MCP server for real.
- Venv active: `source .venv/bin/activate` (run `./scripts/venv_setup.sh` first on a fresh checkout).
- `.env` populated: a model key (`ANTHROPIC_API_KEY` by default) and `DB2i_HOST` / `DB2i_USER` / `DB2i_PASS`. `evals/__main__.py` loads `.env` itself, defaults `MCP_URL` to `http://localhost:3010/mcp` for host runs, and points the LLM judge at `AGENT_MODEL` (override with `EVALS_JUDGE_MODEL`).

## 1. Run the suite

```bash
python -m evals --tag smoke            # fast core: schema discovery, status, injection, PTF
python -m evals --tag release          # all cases
python -m evals --name <case>          # single case while iterating
python -m evals --json-output out.json # machine-readable results (carries judge_reason)
python -m evals -v                     # stream the full agent run with rich panels
```

Output ends with a summary block. Exit code is 0 on all-pass, non-zero on any failure or error.

**Arriving from "it was red last week"?** Eval history lives in Postgres (`db.get_eval_runs()` — also visible at os.agno.com), so find which case failed and when, then reproduce it locally with `python -m evals --name <case>` before diagnosing. A historical failure that won't reproduce is usually environment (the IBM i was down, a rate limit) — note it, don't chase it with prompt edits.

Stderr noise around MCP teardown (`RuntimeError: Event loop is closed`, httpx timeouts) at the end of a run is harmless — only the `Eval Summary` table and exit code count.

## 2. Diagnose each failure

For every failed case, decide which kind of failure it is and fix at the appropriate layer:

| Symptom | Likely cause | Where to fix |
|---|---|---|
| Judge fails, "answer is right but missing X" | Agent's instructions don't push for X | `agents/<slug>_agent.py` — tighten the rule in its own mission section |
| Judge fails, response is fabricated | Agent hallucinated when a query failed or the data doesn't exist | Strengthen the agent's own instructions ("if the tool errors or returns nothing, say so plainly") — `ERROR_HANDLING` already forbids fabrication, so the fix is reinforcing it for this agent's cases, not editing `common.py` |
| Reliability fails: "missing tool X" | Agent didn't call the expected tool on this prompt | (a) Strengthen the routing rule in instructions, OR (b) the case is too narrow — the ask is answerable through a sibling tool in the same toolset; broaden `expected_tool_calls` or drop the assertion |
| Reliability fails and the expected tool is confirmation-gated (`execute_sql`, lockdown tools) | Gated tools pause — they never fire in an eval run | The case is wrong by construction: reframe its input to a read-only path, or assert the refusal/pause side in `criteria` instead. Never un-gate the tool to make a case pass |
| Run comes back `PAUSED` with empty content | The case input invited a gated tool | Same fix as above — the input, not the agent, is the bug |
| Judge fails because the rubric names a value (a library, a PTF level, a count) the system doesn't have | Rubric pinned system state | Rewrite the criteria shape-based ("names at least one concrete group, or clearly reports the data is unavailable") — the suite must pass on any IBM i |
| Tool fires but errors (SQL error in the MCP server logs) | The tool's SQL is broken on this system (Tech Refresh level, renamed view) | Reproduce with `ibmi sql "<the statement>"`, fix the YAML in `tools/*.yaml`, regenerate with `uv run python parse_mcp_tools.py` — a tool fix, never a prompt fix |
| `ibmi-sample` cases fail with "schema not found" | SAMPLE isn't installed on the target system | Environment finding — the shipped case's criteria tolerate it; if a user case doesn't, adopt the same either/or pattern (`CALL QSYS.CREATE_SQL_SAMPLE('SAMPLE')` installs it if they'd rather) |
| Same case flips PASS/FAIL across consecutive runs with no code change | Judge variance — rubric is too loose | Re-run 2-3 times to confirm; if it keeps flipping, tighten the case's `criteria` (more specific, more falsifiable) |
| Single case fails on full suite but passes alone | Transient flake, model rate limit, or a slow IBM i query hitting the timeout | Re-run in isolation; if it passes, re-run the suite. Persistent timeouts on a healthy system → raise that case's `timeout_seconds`, not the agent |
| Many cases fail at once with connection/tool errors | MCP server down, bad `DB2i_*` credentials, or the IBM i unreachable | `podman logs ibmi-mcp-server --tail 50`. Environment — do NOT paper over with prompt edits |
| `eval_db` write errors | Postgres down | `podman compose up -d agentos-db`; check `podman logs agentos-db` |

**Rule:** never weaken a case to make it green. Edit a case only when the assertion was wrong (overspecified rubric, wrong tool name, a value-pinned criterion, a gated-tool expectation). Catching a real regression is the whole point.

Quick test for "wrong assertion vs. real regression": read both sides — the agent's actual response next to the judge's stated reason (`--json-output` carries `judge_reason`). If the response looks correct against the user's intent but the rubric flagged a missing detail, the rubric was overspecified. If the response is genuinely wrong, the agent's instructions need work.

And when you touch a case, check the green is earned, not just present: the expected tool actually fired, and the rubric can't be satisfied by a shortcut (answering from general IBM i knowledge without querying the system). Repair means making red green *and* making green honest.

## 3. Fix scope

In scope from this prompt:

- `agents/<slug>_agent.py` — instructions, toolset composition.
- `evals/cases.py` — when an assertion was genuinely wrong (per the rule above).
- `tools/*.yaml` — when the tool's own SQL is broken: validate the fix with the `ibmi` CLI first (read-only statements only), then **always** `uv run python parse_mcp_tools.py`.

Out of scope (flag for the user, don't do):

- Removing cases.
- Editing `db/`, `app/`, or `evals/__main__.py` to make a case pass.
- Weakening the shared blocks in `agents/utils/common.py` to dodge an adversarial case — a failing injection or fabrication probe is a real finding on every agent at once.
- Removing a tool from `requires_confirmation_tools`, or flipping a tool's `readOnly` posture.

For agent quality issues that need fast iteration against a live container (cURL probes, instruction tweaks), hand off to [`improve-agent`](../improve-agent/SKILL.md) — its probe loop is faster than running the eval suite per change. If the change is user-driven (add a tool, fix a known bug), use [`extend-agent`](../extend-agent/SKILL.md) instead.

## 4. Re-run and stop

After each fix, re-run the failing case:

```bash
python -m evals --name <case>
```

When all targeted cases pass, run the release-tagged cases once more to confirm nothing regressed:

```bash
python -m evals --tag release
```

Stop when `python -m evals --tag release` exits 0 **and** prints an `Eval Summary` block. If a re-run aborts mid-stream (no summary, regardless of exit code), treat it as inconclusive — re-run before declaring green.

## 5. Add a new case (if needed)

If diagnosing a failure reveals a missing assertion, add it to [`evals/cases.py`](../../../evals/cases.py). (That's the one authoring move that belongs here — for coverage-shaped work, an agent with no cases at all, or mining sessions for scenarios, hand off to [`create-evals`](../create-evals/SKILL.md), which carries the full IBM i case-writing rules: toolset-grounded assertions, read-only inputs, value-free rubrics.)

Run `python -m evals --name <case>` to confirm it passes against the current agent. Commit the new case alongside any fixes.

## 6. Track regressions over time

Every case logs to Postgres via `db=eval_db`. Connect your AgentOS at [os.agno.com](https://os.agno.com) and view eval history — useful for catching slow drift. There's no scheduler in this template: the suite runs when someone runs it, so make `--tag smoke` a habit before pushes and `--tag release` before anything public.

---

## Reference: Case shape

`Case` ships with agno (`from agno.eval import Case`) — the template declares cases, agno runs them:

```python
@dataclass(frozen=True)
class Case:
    name: str
    input: str
    agent: Agent
    tags: tuple[str, ...] = ()
    timeout_seconds: int | None = None

    # Judge (LLM rubric, binary pass/fail): set to enable.
    criteria: str | None = None
    judge_model: Model | None = None  # per-case judge override

    # Reliability (tool-call assertion): set to enable.
    expected_tool_calls: tuple[str, ...] | None = None
    allow_additional_tool_calls: bool = True

    # Lifecycle hooks: setup runs before the agent; its return value is passed to
    # teardown, which always runs (pass, fail, error, timeout).
    setup: Callable | None = None
    teardown: Callable | None = None
```

The runner calls `agent.arun()` once per case and feeds the response into both checks, so cases that set both fields cost one agent run, not two.

Two template-specific notes. This suite needs no setup/teardown hooks — containment here is the read-only rule (cases never drive modifying tools), not snapshot-diff cleanup; if you ever add a case that mutates external state, that case is wrong for this suite. And the suite-wide judge follows `AGENT_MODEL` (see `evals/__main__.py`) — if judge verdicts read strangely after a provider switch, check which model is judging before blaming the rubric.
