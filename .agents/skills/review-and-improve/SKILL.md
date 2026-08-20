---
name: review-and-improve
description: Repo-wide drift sweep for public-readiness — diff docs against code, confirm every agent is registered and reachable, every env var documented, every toolset name resolves, every doc path exists, and scripts behave as advertised; auto-fix mechanical drift and flag the rest. Use before a public release or after a refactor.
---

# Review and Improve

> _**Coding-agent workflow** — a `/slash-command` your coding agent (Claude Code, Codex, others) runs while developing this repo. Invoke it by name (e.g. `/review-and-improve`) or describe the task and it triggers automatically._

You are sweeping the whole repo for public-consumption readiness — docs accuracy, every agent reachable, scripts that do what the docs claim, no stale env vars, toolsets in sync, format + validate clean. Most drift is mechanical (renamed file, missing entry in `.env.example`, new agent not in the layout tree) and you fix it in place. The rest is a punch list you surface to the user.

This is a **recurring sweep** — on a clean repo it ends with "no diffs"; on a dirty one it brings everything back to coherent.

[`AGENTS.md`](../../../AGENTS.md) is the source of truth for repo conventions; [`CLAUDE.md`](../../../CLAUDE.md) is a symlink to it — edit once, both update.

## What you auto-fix vs. what you flag

**Auto-fix in place** (no asking):

- Stale file paths in any doc.
- Missing entries in [`.env.example`](../../../.env.example) for env vars the code or compose actually reads.
- Stale entries in `.env.example` nothing reads — delete unless the surrounding comment describes them as optional/future. Flag if intent is unclear.
- Layout trees in `AGENTS.md` / `README.md` missing a registered agent, a doc, or a directory that exists.
- New agent file on disk not yet imported in [`app/main.py`](../../../app/main.py) (add the import + append to `agents=[...]`).
- Missing entry in [`app/config.yaml`](../../../app/config.yaml) for a registered agent (draft quick prompts from its `INSTRUCTIONS`; flag them for the user to refine).
- A stale `tools/toolsets.json` — regenerate with `uv run python parse_mcp_tools.py` (never hand-edit it).
- Missing or wrong cross-links between docs (`docs/*.md`) and the coding-agent skills in [`.agents/skills/*/SKILL.md`](../../../.agents/skills/) (and between skills).
- Single-line factual claim in one doc contradicted by another doc or by code (e.g. one doc says the health endpoint is `/healthz` while the code serves `/health`) — auto-fix the doc, not the code.

**Flag, don't fix** (surface for the user):

- Section-level doc rewrites (a premise is now wrong).
- Code changes beyond imports (instructions, tools, model swaps).
- SQL changes inside [`tools/*.yaml`](../../../tools/) — tool SQL runs against someone's live system; propose, don't apply.
- Dependency edits in [`pyproject.toml`](../../../pyproject.toml).
- Anything in [`db/`](../../../db/), [`compose.yaml`](../../../compose.yaml), [`compose.prod.yaml`](../../../compose.prod.yaml), or [`Dockerfile`](../../../Dockerfile).
- Failing live agents — recommend [`improve-agent`](../improve-agent/SKILL.md) or [`extend-agent`](../extend-agent/SKILL.md); don't fix here.
- Failing eval cases — recommend [`eval-and-improve`](../eval-and-improve/SKILL.md); don't fix here.

## 0. Preconditions

- Live stack reachable: `curl -sSf http://localhost:8000/health` and `curl -sSf http://localhost:3010/healthz` return 200. If not, ask the user to `podman compose up -d --build` first — Step 4 needs a live stack.
- Recommend a feature branch so auto-fixes are easy to revert: `git checkout -b review/$(date +%Y%m%d)`.

## 1. Scope check

Restate the surface area in 4-5 lines so the user can redirect before you read everything:

- Top-level docs: [`README.md`](../../../README.md), [`AGENTS.md`](../../../AGENTS.md), [`.env.example`](../../../.env.example).
- Field manuals: [`docs/*.md`](../../../docs/).
- Coding-agent skills: [`.agents/skills/*/SKILL.md`](../../../.agents/skills/) (frontmatter `name` matches the folder; `description` is trigger-rich; relative links resolve from two levels deep, i.e. `../../../`).
- Code: [`app/`](../../../app/), [`agents/`](../../../agents/), [`db/`](../../../db/), [`evals/`](../../../evals/), [`scripts/`](../../../scripts/), [`parse_mcp_tools.py`](../../../parse_mcp_tools.py).
- Configs: [`compose.yaml`](../../../compose.yaml), [`compose.prod.yaml`](../../../compose.prod.yaml), [`Dockerfile`](../../../Dockerfile), [`pyproject.toml`](../../../pyproject.toml), [`tools/`](../../../tools/) YAMLs (schema validated live from the ibmi-mcp-server repo by `validate.sh`).

Skip: `.venv/`, `*_cache/`, `.git/`, `*.egg-info/`, anything generated (read `tools/toolsets.json` only to verify it's fresh).

If the user has a specific concern (recent refactor, prepping a release, a doc they think is stale), fold it in now.

## 2. Inventory

Read every file in scope. Build a mental model of:

- **Registered agents** — the literal `agents=[...]` list in `app/main.py` (this repo has no registry or autoloader by design).
- **Agent files on disk** — what's in [`agents/`](../../../agents/) (excluding `utils/`).
- **Toolsets** — every `get_toolset("...")` name used in agent files, and what `tools/toolsets.json` actually defines.
- **Env vars actually read** — grep `getenv` / `os.environ` in code, plus `${...}` interpolations and `environment:` keys in `compose.yaml`.
- **Manifest** — entries in [`app/config.yaml`](../../../app/config.yaml).
- **Scripts** — for each file in [`scripts/`](../../../scripts/), what it actually does.

Don't write anything yet — read first, fix once.

## 3. Consistency pass

The bulk of the work. Diff each pair; auto-fix per the rules at the top.

| Check | Where | Common drift |
|---|---|---|
| Every agent file is registered | [`agents/`](../../../agents/) ↔ `app/main.py` | New agent file not imported |
| Every registered agent has a manifest entry | `app/main.py` ↔ `app/config.yaml` | Agent added without quick prompts |
| Every `get_toolset()` name resolves | agent files ↔ `tools/toolsets.json` | Toolset renamed in YAML, agent not updated |
| `toolsets.json` is fresh | `tools/*.yaml` ↔ regenerated output | YAML edited without `uv run python parse_mcp_tools.py` |
| Every env var in code/compose is documented | code + compose grep ↔ README env table + `.env.example` | New var added without entries |
| Every var in `.env.example` is read somewhere | `.env.example` ↔ code + compose grep | Stale var nobody reads |
| Every path mentioned in docs exists | `README.md`, `AGENTS.md`, `docs/*.md`, `.agents/skills/*/SKILL.md` ↔ filesystem | Renamed or deleted file |
| Every script mentioned in docs is real + does what's claimed | docs ↔ `scripts/` | Renamed or behavior drifted |
| Layout trees match reality | `README.md` Project Structure, `AGENTS.md` Repo layout | New file or dir missing from the tree |
| Health endpoints in docs match code | docs ↔ agno's `/health`, MCP server's `/healthz` | Wrong endpoint claimed |
| MCP server version pin consistent | `.env.example` `MCP_SERVER_VERSION` ↔ `compose.yaml` default | Bumped in one place only |
| Skill frontmatter + links resolve | `.agents/skills/*/SKILL.md` ↔ folder name + `../../../` targets | name≠folder, broken path, dead cross-skill link |
| Skill symlinks resolve | `.claude/skills` and `.bob/skills` → `../.agents/skills` | Symlink missing or dangling |
| MCP config symlink resolves | `.mcp.json` → `.bob/mcp.json` (the real file) | Symlink replaced by a stale copy, or dangling |
| `.bob/mcp.json` servers and the docs that reference them agree | `.bob/mcp.json` ↔ docs + skills | URL changed, server renamed, `agentos` entry dropped |
| MCP interface claim matches code | docs ↔ `mcp_server=True` in `app/main.py` | `/mcp` promised in docs but flag flipped off |
| Eval cases reference real agents + tools | [`evals/cases.py`](../../../evals/cases.py) ↔ `agents/` + `tools/toolsets.json` | Agent renamed or tool removed from a toolset |
| "Don't add" cuts still hold | `AGENTS.md` deliberate-cuts list ↔ codebase | A registry/CLI/auth layer crept in undocumented |

## 4. Live stack smoke

First, confirm the live container serves *this* repo's agents:

```bash
curl -s http://localhost:8000/agents | jq -r '.[].id' | sort
```

If the list doesn't match the ids in `agents=[...]`, stop and surface it — the container is bound to a different checkout or needs a restart; smoking the wrong code is worse than skipping.

Then hit each registered agent with one of its quick prompts from `app/config.yaml`:

```bash
curl -sS -X POST http://localhost:8000/agents/<slug>/runs \
  -F "message=<one of the quick prompts for this slug>" \
  -F "user_id=claude-review" \
  -F "stream=false" \
  -o /tmp/review-<slug>.json \
  -w "HTTP %{http_code} in %{time_total}s\n"

jq -r '.content // .' < /tmp/review-<slug>.json | head -20
```

Pass = HTTP 200, non-empty content, no errors in `podman logs agentos-api --since 30s`. Two expected non-failures: a probe that reaches a `requires_confirmation_tools` member (e.g. `execute_sql` on `ibmi-text2sql`) returns `"status": "PAUSED"` — correct HITL behavior; and `ibmi-sample` erroring because the SAMPLE schema isn't on the target system is an **environment finding**, not a code bug — report it as such.

Quality issues (plausible-but-wrong answer, wrong tool fired) are out of scope — note them and recommend [`improve-agent`](../improve-agent/SKILL.md) or [`extend-agent`](../extend-agent/SKILL.md).

## 5. Format + validate

```bash
source .venv/bin/activate  # ./scripts/venv_setup.sh first if it doesn't exist
./scripts/format.sh
./scripts/validate.sh
```

`format.sh` auto-fixes. `validate.sh` runs ruff + mypy + the tool-YAML schema validation. If it fails, surface the errors verbatim — they usually point at real bugs introduced since the last sweep, not noise to suppress.

## 6. Evals (ask before running)

`python -m evals --tag release` costs model calls and runs real (read-only) SQL against the configured IBM i. Ask before running:

> Run `python -m evals --tag release` to confirm no agent regressed? (Hits the model API and your IBM i; takes a few minutes.)

If yes, run it. If any case fails, add it to "Needs your call" with [`eval-and-improve`](../eval-and-improve/SKILL.md) as the recommended follow-up. If the user declines, skip this step entirely — it does not affect the rest of the report.

## 7. Report

If nothing was fixed and nothing flagged, print: *"Repo is consistent and the live stack is healthy. No follow-up needed."* No commit suggested.

Otherwise, three blocks, in order:

**Fixed automatically** — one line per change, with file path. Terse.

**Needs your call** — flagged items, ranked by severity. For each: one-line description, file (and line if useful), recommended action.

**Diff + next step**:

```bash
git diff --stat
```

- Suggested commit message — `chore: review-and-improve sweep` plus one short bullet per fix bucket.
- Recommended follow-up — usually [`improve-agent`](../improve-agent/SKILL.md) (if a live agent looked off) or [`eval-and-improve`](../eval-and-improve/SKILL.md) (if evals failed).

A clean sweep takes 3-5 minutes (10+ if the venv needs creating). A dirty one is 15-30, mostly because live smoke surfaces agent regressions you have to triage.
