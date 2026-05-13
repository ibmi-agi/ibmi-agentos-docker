# IBM i AgentOS Template

A starter repo for building, improving, and shipping IBM i agents on [Agno AgentOS](https://docs.agno.com). Three reference agents (Text-to-SQL, SQL Service Guide, System Health) are wired up out of the box, and Claude Code prompts under `docs/` drive the full lifecycle — create, improve, extend, eval, review.

The template is designed so a coding agent can read, edit, and improve the platform end-to-end: agent code, traces, tool YAMLs, and docs all live in one repo.

## What you get

| Piece | Where |
|---|---|
| 3 reference agents | `agents/{text2sql,sql_service_guide,system_health}.py` |
| IBM i tools (MCP server) | `tools/*.yaml` → `tools/toolsets.json` via `parse_mcp_tools.py` |
| Postgres + pgvector for sessions, memory, traces, knowledge | `db/` + `compose.yaml` |
| Shared knowledge base (Ollama embeddings by default) | `knowledge/` + `app/knowledge.py` + `scripts/load_knowledge.py` |
| Learning module (Agno LearningMachine) | `learning/` |
| Web research via Parallel.ai ContextProvider | `agents/utils/web_context.py` |
| Optional multi-user auth (RSA + AES) | `auth/` + `compose.auth.yaml` |
| Claude Code prompts for the agent lifecycle | `docs/{create-new,improve,extend,eval-and-improve,review-and-improve}-agent.md` |

## Quickstart

```bash
git clone <this-repo> ibmi-agentos
cd ibmi-agentos
cp example.env .env
# Edit .env — set DB2i_HOST/USER/PASS and ANTHROPIC_API_KEY (or another provider)
docker compose up -d
```

Four services come up: `agentos-db` (Postgres + pgvector), `ollama` (local embedder for the knowledge base — pulls `qwen3-embedding:0.6b` on first boot, ~700 MB download), `ibmi-mcp-server` (IBM i tools), `agentos-api` (FastAPI). Health probes:

```bash
curl -sSf http://localhost:8000/healthz
curl -sSf http://localhost:3010/healthz
curl -s http://localhost:8000/agents | jq '.[] | .id'
# → ["ibmi-text2sql", "ibmi-sql-service-guide", "ibmi-system-health"]
```

One-time setup: seed the knowledge base from `knowledge/`:

```bash
uv run python scripts/load_knowledge.py
```

Talk to an agent from the terminal:

```bash
uv run python cli.py --agent text2sql --prompt "list schemas containing QSYS"
uv run python cli.py --agent system-health --prompt "what is current CPU utilization?"
uv run python cli.py                                  # interactive REPL
```

Or via HTTP:

```bash
curl -s -X POST -H "Content-Type: application/json" \
    http://localhost:8000/agents/ibmi-text2sql/runs \
    -d '{"input": "describe QSYS2.SYSTABLES"}'
```

## How it fits together

```
cli / curl ──▶ agentos-api ──▶ ibmi-mcp-server ──▶ IBM i (Db2 for i)
                  │                  │
                  │                  ▼
                  │              tools/*.yaml
                  │              (read by MCP server on boot)
                  ▼
              Postgres (agentos-db)
              ├── sessions / memory / traces
              ├── learning  (user_profile, entity_memory, session_context, ...)
              └── ibmi_knowledge (PgVector — embedded by ollama)
```

- **Agents** declare themselves in `agents/<name>.py` and register in `app/main.py`'s literal `agents=[...]` list (no registry / autoloader — explicit imports).
- **Tools** live in `tools/*.yaml`, validated and compiled into `tools/toolsets.json` by `parse_mcp_tools.py`. Agents pick toolsets by name via `ibmi_tools(["performance"])`.
- **Knowledge** lives in `knowledge/{tables,queries,business}/`, ingested into PgVector via `scripts/load_knowledge.py`. Every agent searches it on every turn (`search_knowledge=True`).
- **The model provider** is one env var: `DEFAULT_MODEL_ID=anthropic:claude-sonnet-4-6` (default). Swap to OpenAI / Gemini / Groq / Ollama by changing the prefix — Agno's `get_model()` resolves it.

## Working with Claude Code (the intended workflow)

Open the repo in [Claude Code](https://claude.com/claude-code) and paste any of these prompts:

| Prompt | What it does |
|---|---|
| `Run docs/create-new-agent.md` | Socratic walkthrough that scaffolds a new IBM i agent end-to-end |
| `Run docs/extend-agent.md` | Adds a new toolset YAML to an existing agent |
| `Run docs/improve-agent.md` | Probe-loop hardening — derives probes from the agent's contract, runs them, edits until they pass |
| `Run docs/eval-and-improve.md` | Runs the IBM i eval suite (`evals/cases.py`), diagnoses failures, fixes |
| `Run docs/review-and-improve.md` | Sweep for drift (stale `toolsets.json`, missing env vars, deployment hygiene) |

Plus three reference docs:

- [`docs/ibmi-mcp-server.md`](docs/ibmi-mcp-server.md) — how the MCP server, tool YAMLs, and `parse_mcp_tools.py` fit together
- [`docs/knowledge-base.md`](docs/knowledge-base.md) — how `knowledge/`, the embedder, and `scripts/load_knowledge.py` work
- [`docs/auth-optional.md`](docs/auth-optional.md) — how to opt in to multi-user IBM i credentials

## Editing the agents

After editing a Python file under `agents/`, `app/`, `db/`, or `auth/`, the uvicorn reloader picks it up automatically (development mode). After adding a **new** agent file you must restart:

```bash
docker compose restart agentos-api
```

After editing a `tools/*.yaml`:

```bash
uv run python parse_mcp_tools.py     # regenerates tools/toolsets.json
# YAML_AUTO_RELOAD=true in compose, so ibmi-mcp-server picks up YAML changes automatically
```

## Validation gate (before committing)

```bash
bash scripts/format.sh        # ruff format
bash scripts/validate.sh      # ruff check + mypy
uv run python -m evals -v     # eval suite
```

If your fork derives from another project, run a brand-string scrub too — see [`docs/review-and-improve.md`](docs/review-and-improve.md) §1.

The CI workflow at `.github/workflows/validate.yml` runs the same lint + type-check on every push.

## Production deployment

The template targets **Docker** or **Podman** — `compose.yaml` is the source of truth, no platform-specific glue. Bring it up the same way in production as in dev, with a separate env file for secrets:

```bash
docker compose --env-file .env.production up -d
# or
podman compose --env-file .env.production up -d
```

For an image-based deploy (push the API container to a registry, run it next to your IBM i):

```bash
docker build -t your-registry/ibmi-agentos:latest .
docker push  your-registry/ibmi-agentos:latest
```

Then run on the production host with a `compose.yaml` that pulls the published image instead of `build:`. The IBM i MCP server image (`ghcr.io/ibm/ibmi-mcp-server`) is already published — no build step needed.

**Two things you own at deploy time:**

1. **Network** to the IBM i. The MCP server needs Db2-for-i port 8076 reachable. Co-locate it on a host inside the IBM i's network, or open a VPN tunnel.
2. **Where Postgres lives.** `agentos-db` in the template is a single-host container with a local volume — fine for a small deployment, but for HA replace it with a managed Postgres + pgvector (e.g. AWS RDS with the extension enabled, Aiven, etc.) and point `DB_HOST` at it.

## Multi-user auth (opt-in)

Default is single-tenant (one shared IBM i identity from `.env`). For per-user identities:

```bash
echo "AUTH_ENABLED=true" >> .env
bash scripts/generate_mcp_keys.sh
docker compose -f compose.yaml -f compose.auth.yaml up -d
```

Then create an API key and register a connection. Full walkthrough: [`docs/auth-optional.md`](docs/auth-optional.md).

## License

MIT. See `LICENSE`.
