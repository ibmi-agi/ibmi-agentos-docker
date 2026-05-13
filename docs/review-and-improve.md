# Review and Improve the IBM i Template

> Claude Code prompt. Open Claude Code in this repo and paste:
> `Run docs/review-and-improve.md`

You are auditing the repo for drift between what it documents and what it does. IBM i templates rot in specific ways: a tool YAML changes but `toolsets.json` is stale, a new env var is read in code but never landed in `example.env`, the MCP server version bumps but `compose.yaml` still pins the old one. Walk the checklist, auto-fix the mechanical issues, and flag the structural ones for the user.

This is a **read mostly, edit surgically** loop. Don't refactor anything not on the list.

## 0. Preconditions

Repo is clean (`git status` shows no unrelated work-in-progress). If dirty, ask the user to stash or commit first — you don't want this audit's edits commingled with theirs.

## 1. Brand-string scrub

The template ships generic — no upstream project's name or env-var prefix should leak in. Pick the brand strings that belong to **your** fork's origin and grep for them.

For a fork that started life as project `XYZ`:

```bash
BRAND='xyz|Xyz|XYZ_'
grep -rin -E "$BRAND" . --exclude-dir=.git --exclude-dir=.venv --exclude='LICENSE'
```

Every match must be removed or, if functional (e.g. an env var name read by external infra), explicitly justified. Common sources:
- A copy-paste from the upstream fork
- A leftover env var name in a script

## 2. toolsets.json freshness

The MCP tool catalog (`tools/toolsets.json`) is generated from `tools/*.yaml`. If any YAML is newer than the JSON, the catalog is stale.

```bash
find tools -name '*.yaml' -newer tools/toolsets.json -print
```

If anything prints, regenerate:

```bash
uv run python parse_mcp_tools.py
```

Also confirm every toolset name referenced by an agent's `ibmi_tools([...])` call exists in `toolsets.json`:

```bash
python3 -c "
import json, re, pathlib
ts = set(json.loads(pathlib.Path('tools/toolsets.json').read_text()).keys())
for p in pathlib.Path('agents').glob('*.py'):
    for m in re.findall(r'ibmi_tools\(\s*\[([^\]]+)\]', p.read_text()):
        for name in re.findall(r'\"([^\"]+)\"', m):
            if name not in ts:
                print(f'  MISSING in toolsets.json: {name} (referenced by {p.name})')
"
```

## 3. example.env matches reality

For every `getenv("…")` call in the codebase, the variable must appear in `example.env` (commented or active). Otherwise users won't know it's a knob.

```bash
python3 -c "
import re, pathlib
declared = set(re.findall(r'^[# ]*([A-Z][A-Z0-9_]*)=', pathlib.Path('example.env').read_text(), re.M))
read = set()
for p in list(pathlib.Path('.').rglob('*.py')) + list(pathlib.Path('.').rglob('*.sh')):
    if any(x in str(p) for x in ('.venv', '.git', '_archive')):
        continue
    for m in re.findall(r'getenv\([\"\\']([A-Z_][A-Z0-9_]*)', p.read_text(errors='ignore')):
        read.add(m)
    for m in re.findall(r'\\$\\{([A-Z_][A-Z0-9_]*)', p.read_text(errors='ignore')):
        read.add(m)
missing = sorted(read - declared - {'PATH','HOME','PWD','USER','HOSTNAME','SHELL'})
if missing:
    print('Vars read but not in example.env:')
    for v in missing: print(f'  - {v}')
"
```

For each missing var, add a commented-out line to `example.env` with a one-line explanation.

## 4. compose.yaml env wiring matches agentos-api needs

Every var the FastAPI app reads at runtime must reach the container. Open `compose.yaml`, locate the `agentos-api` service's `environment:` block, and confirm every var read by `app/`, `agents/`, `auth/` either:
- Has an explicit entry in `environment:`, **or**
- Is loaded via `env_file: .env`

## 5. Agent registry matches imports

Every agent module in `agents/` (except `__init__.py`, `config.py`, and `utils/`) should appear in `app/main.py`'s `agents=[]` list. Conversely, every name in the list must resolve to an importable agent.

```bash
ls agents/*.py | grep -v -E '(__init__|config)\.py' | sed 's|agents/||; s|\.py$||'
grep -E 'from agents\.' app/main.py
```

Diff the two lists by eye — fix any drift.

## 6. requirements.txt vs pyproject.toml

```bash
bash scripts/generate_requirements.sh
git diff requirements.txt
```

If the diff is non-empty, `pyproject.toml` was changed without regenerating. Commit the diff or revert the dep change.

## 7. MCP server version sanity

The template pins `MCP_SERVER_VERSION` in `example.env` and uses it via `${MCP_SERVER_VERSION:-…}` in `compose.yaml`. Confirm both reference the same default. If a user has bumped one but not the other, point them at [`docs/ibmi-mcp-server.md`](ibmi-mcp-server.md) for the upgrade flow.

## 8. Compose stack still boots clean

```bash
docker compose config -q              # validate compose.yaml without starting anything
docker compose config -q -f compose.yaml -f compose.auth.yaml  # with auth overlay
```

Either command exits non-zero on syntax / reference errors. Compose is the deploy story — keep it green.

## 9. Auth module integrity (if installed)

If `auth/` is present:

```bash
grep -rin -E "$BRAND" auth/  # same regex as step 1
python3 -c "
for m in ['middleware','mcp_tokens','connections','context','service','encryption']:
    __import__(f'auth.{m}')
    print(f'  ok: auth/{m}.py imports')
"
```

If imports fail, check that the optional deps installed: `uv pip install -e '.[auth]'`.

## 10. Lint + type-check

```bash
bash scripts/validate.sh
```

Should be green. If not, fix in scope (no refactors).

## 11. Smoke test

```bash
docker compose up -d
sleep 5
curl -sSf http://localhost:8000/healthz
curl -sSf http://localhost:3010/healthz
curl -s http://localhost:8000/agents | jq '.[] | .id'
```

All three should succeed and the agent list should match what `app/main.py` registers.

## 12. Summary

Tell the user:
- What was stale and is now fresh (toolsets.json, requirements.txt)
- What was missing and is now documented (example.env additions)
- What you couldn't auto-fix and they need to decide on (structural drift, missing prod deploy hooks, etc.)

Let the user commit.
