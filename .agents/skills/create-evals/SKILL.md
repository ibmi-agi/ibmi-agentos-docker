---
name: create-evals
description: Author eval coverage for an IBM i agent — map what its INSTRUCTIONS and shared guardrail blocks promise, mine real sessions from Postgres for scenarios, ground tool assertions in tools/toolsets.json, then write, run, and audit read-only Case entries in evals/cases.py. Use when the user wants evals created, coverage added, or an agent's behavior pinned down as tests. To repair a failing suite, use eval-and-improve instead.
---

# Create Evals

> _**Coding-agent workflow** — a `/slash-command` your coding agent (Claude Code, Codex, others) runs while developing this repo. Invoke it by name (e.g. `/create-evals`) or describe the task and it triggers automatically._

You're giving an IBM i agent eval coverage: turning what it promises into `Case` entries in [`evals/cases.py`](../../../evals/cases.py) that catch regressions from now on. The suite only watches what someone wrote down — the template ships cases for its six reference agents, but a user's own agents are invisible to it until this skill runs. Every case here runs real SQL against the configured IBM i system, which shapes the whole craft: **cases are read-only by construction, and rubrics judge the shape of groundedness, never the values** — system state (CPU load, PTF levels, user lists) is different on every box and every run.

This is the **authoring** skill. If the suite is failing and needs diagnosis, that's [`eval-and-improve`](../eval-and-improve/SKILL.md); if the agent itself needs hardening against its instructions, that's [`improve-agent`](../improve-agent/SKILL.md). Preconditions match eval-and-improve's Step 0: `agentos-db` and `ibmi-mcp-server` up, venv active, `.env` populated.

**Be self-driving:** the repo and the database answer most questions — read them instead of asking. The user's judgment is for what only they know: which jobs matter most and which failures would hurt. One pick per exchange, recommendation first.

## 1. Pick the agent

If the user named one, that's the pick. Otherwise compare `agents/` against the cases in `evals/cases.py` and recommend the agent with the least coverage — usually the one they built themselves, since template agents come covered. Name your pick and why in one line; roll on unless they object.

## 2. Map what it promises

Read the agent's file. Two layers promise testable behavior:

- **Its own mission steps** — every "always check X first", "present Y as a table", "recommend with priority levels" is a case waiting to be written.
- **The shared blocks** from [`agents/utils/common.py`](../../../agents/utils/common.py) its `INSTRUCTIONS` interpolate — each is a standing promise: `GUARDRAILS` (injection defense, credential redaction, confirmation before destructive ops), `DATA_HANDLING` (indicate truncation, prefer read-only), `ERROR_HANDLING` (never fabricate on failure — the strongest rubric material in the file), `AUDIT` (states which tools ran), `WEB` (outside-world questions route to `query_web`).

Then map the tools: open [`tools/toolsets.json`](../../../tools/toolsets.json) and read the member names of the agent's `get_toolset("...")` sets (text2sql uses the MCP server built-ins listed in its file instead). These exact names are your reliability material — `expected_tool_calls` entries that don't match them fail forever.

One check has teeth: **can the agent reach modifying tools?** Look for `requires_confirmation_tools` members (like `execute_sql` on text2sql) and toolset members whose YAML sets `readOnly: false` (the security toolsets carry lockdown tools). Case inputs must never drive them — a report-only framing in the input (the shipped `security_audit_reports_findings` shows it) is this suite's containment, the way snapshot hooks are in agno's own template. And never put a gated tool in `expected_tool_calls`: it pauses for confirmation instead of firing, so the assertion can only fail.

## 3. Mine the platform

The platform records how the agent actually gets used — read it before inventing scenarios:

```python
from db import get_postgres_db
db = get_postgres_db()
# deserialize=False keeps the (rows, total) tuple shape and returns plain dicts
sessions, _ = db.get_sessions(component_id="<agent-id>", limit=20, deserialize=False)
asks = [run["input"]["input_content"] for s in sessions for run in (s.get("runs") or []) if run.get("input")]
evals, _ = db.get_eval_runs(limit=20, deserialize=False)   # what's already covered, what's flaky
```

Real session inputs make the best case inputs — they're what the agent will face again. Two rules: **a recorded answer is a scenario, never a golden answer** (the agent may have been wrong that day; the rubric states what a correct answer looks like, not what yesterday's said), and a fresh platform with no sessions is fine — derive scenarios from `INSTRUCTIONS` instead, the same fallback improve-agent's probes use. One IBM i-specific trade-off to surface: a mined ask that names a real library or schema makes a case that only passes on *this* system. That's fine for the user's own suite — just say so — but keep anything meant to stay portable on `QSYS2` services every IBM i has.

## 4. Propose what to test

Offer 2–3 capabilities, grounded in the map and the mining: for each, a one-line scenario and what a pass proves. Lead with a recommendation — the capability closest to the agent's core job, or the one real sessions hit most. Skip proposals the suite already covers. One exchange: they pick, or their own words redirect you.

## 5. Write the case

Inside the `CASES` tuple of [`evals/cases.py`](../../../evals/cases.py), before its closing paren — add the marker comment there if this is the first: `# --- Your cases — authored by /create-evals ---`. Case names must be unique across the file (grep for yours first — duplicates run without error and muddy the shared history). The shape:

```python
Case(
    name="<agent>_<capability>",
    agent=<the_agent_instance>,        # import it at the top like the shipped cases
    input="<scenario — a real session ask, or one derived from INSTRUCTIONS>",
    tags=("release",),                 # add "smoke" only for fast, always-runnable core checks
    timeout_seconds=150,               # live SQL + model calls — 120-180s is the working range
    criteria="<what a correct answer contains — specific, falsifiable, value-free>",
    expected_tool_calls=("<toolset member name>",),
)
```

The judge and the reliability check answer different questions — **pair them whenever the capability involves a tool**. A rubric alone is gameable: an agent that answers from stale memory without querying can read *correct*; `expected_tool_calls` proves the work happened, the rubric proves the answer used it. The IBM i rules that make a case durable:

- **Ground tool names in `toolsets.json`** (or text2sql's built-ins) — never from memory. A tool YAML rename breaks the assertion; that's a feature, but only if the name was right on day one.
- **Judge shape, never values.** "Reports concrete numbers drawn from the tool output" passes on every system; "reports CPU above 40%" passes on one system on one afternoon. Same for PTF groups, user lists, library names — the shipped cases show the "names at least one concrete X, or clearly reports the data is unavailable" pattern for state that may not exist on the target box.
- **Ask of every rubric: could a stock model with no tools and none of this agent's instructions pass it?** If yes, the case tests nothing — tie the criteria to what only fresh tool output or this agent's `INSTRUCTIONS` can supply.
- **Read-only inputs, report-only framing.** Never write a case whose input invites a modifying or gated tool. If the capability you want to pin *is* a gated flow, the case can assert the refusal/pause side ("declines to execute without confirmation") — never the execution.
- **No "remember this" inputs.** The agents run with agentic memory on; a case that instructs the agent to remember something writes rows into the shared dev DB that nothing cleans up. Keep inputs question-shaped.
- **`query_web`-dependent capabilities** get rubrics of the form "a current X with a source", never today's value — and stay out of `smoke`, which should be deterministic against the system alone.

## 6. Run it, then audit both sides

```bash
python -m evals --name <case>
```

Don't stop at the verdict — read both sides before trusting it, pass or fail:

- **The agent's side:** the actual response, and which tools fired.
- **The judge's side:** its stated reason (`--json-output` carries `judge_reason`).

A case earns its place when a pass is *earned* — right answer, tools fired, rubric only satisfiable by real work — and a fail would be *diagnosable* from the judge's reason. A pass earned once isn't earned: run the case at least twice (three times when the criteria lean on judgment words like "clear" or "actionable") — a verdict that flips between identical runs means the rubric, not the agent, is undecided. First rubrics rarely survive this audit; expect one tightening round. If the audit shows the agent (not the case) is wrong, say so — fixing it is [`improve-agent`](../improve-agent/SKILL.md)'s job, and the failing case you just wrote is exactly the regression test that proves the fix.

Then loop to Step 4 for the next capability, or finish.

## 7. Hand over

Close with what changed and the loop the user now owns: the new cases by name and tag, `git diff evals/cases.py`, a suggested commit message (`eval(<agent>): <what's covered now>`). Then the watch: there's no scheduler in this template, so the suite runs when someone runs it — `python -m evals --tag smoke` before a push, `--tag release` before anything public — and when a run goes red, [`/eval-and-improve`](../eval-and-improve/SKILL.md) picks it up from there. Results log to Postgres either way, visible at os.agno.com.
