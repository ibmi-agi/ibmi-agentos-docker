# Ixora Template — SAMPLE Data Agent for IBM i

A starter template you clone and extend. Out of the box it ships a single agent — **IBM i Data Agent** — wired to the Db2 for i `SAMPLE` library: the demo schema (EMPLOYEE, DEPARTMENT, PROJECT, EMP_ACT, ACT) that's available on every IBM i system. The template gives you the agent, a curated knowledge base of `SAMPLE` table metadata and example queries, validated tool YAMLs, and a tool-authoring loop built around the [`ibmi` CLI](https://ibm-d95bab6e.mintlify.app/cli/overview.md). Use it as the scaffolding for your own IBM i agents.

The template is designed so a coding agent can read, edit, and improve the platform end-to-end: agent code, tool YAMLs, knowledge files, and docs all live in one repo.

## 5-minute quickstart

**Prerequisites:** Docker (or Podman), an IBM i system reachable from your host (with the `SAMPLE` library — present by default on every IBM i), and an API key for your model provider (`ANTHROPIC_API_KEY` by default).

```bash
git clone https://github.com/ibmi-agi/ixora-template && cd ixora-template
cp .env.example .env
# Edit .env — set DB2i_HOST / DB2i_USER / DB2i_PASS and your model key
docker compose up -d --build
```

Three services come up: `agentos-db` (Postgres + pgvector), `ibmi-mcp-server` (IBM i tools), `agentos-api` (FastAPI + the IBM i Data Agent). Verify:

```bash
curl -sSf http://localhost:8000/healthz
curl -s http://localhost:8000/v1/agents | jq '.[] | .id'
# → "ibmi-data-agent"
```

**Optional** — seed the shared knowledge base (table metadata, example queries, business glossary) so the agent can search it on every turn. Requires `OPENAI_API_KEY` in `.env`:

```bash
uv run python scripts/load_knowledge.py
```

The agent works without this step; it just loses the knowledge-search context. See [`docs/knowledge-base.md`](docs/knowledge-base.md).

Talk to the agent from the terminal:

```bash
uv run cli.py --agent ibmi-data-agent --prompt "list the tables in SAMPLE"
uv run cli.py --agent ibmi-data-agent --prompt "show me all employees in department A00"
uv run cli.py                                  # interactive REPL
```

Or via HTTP:

```bash
curl -s -X POST http://localhost:8000/agents/ibmi-data-agent/runs \
    -F "message=describe the EMPLOYEE table" \
    -F "stream=false"
```

The `/agents/{agent_id}/runs` endpoint takes `multipart/form-data` (not JSON) — see the OpenAPI spec at `http://localhost:8000/docs`. Required field is `message`; useful optional fields are `stream`, `session_id`, `user_id`, and `files` for attachments.

## What's inside

- **`agents/`** — the IBM i Data Agent module (`ibmi_data_agent.py`) and its instructions (`agents/instructions/ibmi-data-agent.md`).
- **`tools/`** — SAMPLE-library tool YAMLs (`tools/sample.yaml`), validated against `tools/sql-tools-config.schema.json` and compiled to `tools/toolsets.json` by `parse_mcp_tools.py`.
- **`knowledge/`** — curated SAMPLE-schema KB: one JSON per table under `knowledge/tables/`, reusable example queries in `knowledge/queries/`, business rules and gotchas in `knowledge/business/`.
- **`docs/`** — stored Claude Code prompts for extending the template (add a tool, add an agent, extend the KB).

## Extending the template

The `docs/` directory is the operator's manual. Open the repo in [Claude Code](https://claude.com/claude-code) and paste any of these:

| Prompt | What it does |
|---|---|
| `Run docs/write-new-tool.md` | The canonical tool-authoring loop: explore SAMPLE with the `ibmi` CLI → draft SQL → write the YAML → validate with `parse_mcp_tools.py` → verify live |
| `Run docs/extend-knowledge.md` | Add a table or business rule to the SAMPLE KB; mirrors the tool-authoring loop |
| `Run docs/create-new-agent.md` | Scaffold a second agent alongside the IBM i Data Agent |
| `Run docs/extend-agent.md` | Add tools to (or expand) an existing agent |

Plus reference docs:

- [`docs/ibmi-cli.md`](docs/ibmi-cli.md) — the `ibmi` CLI workflow used throughout the template (install, env, sanity check, the smallest command surface a tool author needs)
- [`docs/tool-design-reference.md`](docs/tool-design-reference.md) — YAML schema, conventions, worked examples; read before authoring any `tools/*.yaml`
- [`docs/ibmi-mcp-server.md`](docs/ibmi-mcp-server.md) — how the MCP server, tool YAMLs, and `parse_mcp_tools.py` fit together
- [`docs/knowledge-base.md`](docs/knowledge-base.md) — how `knowledge/`, the embedder, and `scripts/load_knowledge.py` work
- [`docs/auth-optional.md`](docs/auth-optional.md) — opt in to multi-user IBM i credentials

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
              └── ibmi_knowledge (PgVector — OpenAI embeddings)
```

- **Agents** declare themselves in `agents/<name>.py` and register in `app/main.py`'s literal `agents=[...]` list (no registry / autoloader — explicit imports).
- **Tools** live in `tools/*.yaml`, validated and compiled into `tools/toolsets.json` by `parse_mcp_tools.py`. Agents pick toolsets by name via `ibmi_tools("sample_data")`.
- **Knowledge** lives in `knowledge/{tables,queries,business}/`, ingested into PgVector via `scripts/load_knowledge.py`. The agent searches it on every turn (`search_knowledge=True`).
- **The model provider** is one env var: `DEFAULT_MODEL_ID=anthropic:claude-sonnet-4-6` (default). Swap to OpenAI / Gemini / Groq / Ollama by changing the prefix — Agno's `get_model()` resolves it.

## Editing the agent

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
bash scripts/validate.sh      # ruff check + mypy + schema validation
uv run python -m evals -v     # eval suite
```

`scripts/validate.sh` runs `parse_mcp_tools.py` as part of the gate, so any YAML schema drift fails CI. The CI workflow at `.github/workflows/validate.yml` runs the same checks on every push.

## Production deployment

The template targets **Docker** or **Podman** — `compose.yaml` is the source of truth, no platform-specific glue. Bring it up the same way in production as in dev, with a separate env file for secrets:

```bash
docker compose --env-file .env.production up -d
# or
podman compose --env-file .env.production up -d
```

For an image-based deploy (push the API container to a registry, run it next to your IBM i):

```bash
docker build -t your-registry/ixora-template:latest .
docker push  your-registry/ixora-template:latest
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
