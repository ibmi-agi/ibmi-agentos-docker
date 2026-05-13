# The IBM i Knowledge Base

The template ships with a shared **PgVector** knowledge base — every agent that declares `knowledge=ibmi_knowledge, search_knowledge=True` can search it on every turn. Seed content lives in `knowledge/` at the repo root; a small script ingests it into Postgres.

The pattern is borrowed from Agno's `dash` data-agent template, simplified for a generic IBM i starter.

## Architecture

```
knowledge/             (source of truth — committed to git)
  tables/*.json          Table metadata
  queries/*.sql          Validated example queries (header-tagged)
  business/*.md          Conventions, gotchas, metric definitions
        │
        │ scripts/load_knowledge.py
        ▼
PgVector tables in agentos-db (ibmi_knowledge + ibmi_knowledge_contents)
        │
        │ Embedder: Ollama (qwen3-embedding:0.6b) by default
        ▼
agents see results via search_knowledge=True on every turn
```

## Embedder

The template runs a local **Ollama** container that pulls `qwen3-embedding:0.6b` on first boot. That's the default — no API key required, works offline.

To switch to OpenAI embeddings:

```bash
# in .env
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
# (and set OPENAI_API_KEY)
```

Then re-ingest from scratch (the new model has different dimensions):

```bash
uv run python scripts/load_knowledge.py --recreate
```

Embedder selection lives in [`db/session.py::get_embedder`](../db/session.py) — add other providers there.

## File formats

### `knowledge/tables/*.json` — one file per table

```json
{
  "table_name": "SCHEMA.TABLE",
  "table_description": "One paragraph — purpose, row count order-of-magnitude, the unit of a row.",
  "table_columns": [
    {"name": "COL_NAME", "type": "TYPE", "description": "What it means. Note any gotchas inline."}
  ],
  "data_quality_notes": [
    "Bullet points for things that will bite the Analyst later."
  ]
}
```

**Write descriptions to be copy-pasted into a SQL review comment.** Good: "QUANTITY * unit price before DISCOUNT and TAX." Bad: "Extended price field." See examples under `knowledge/tables/`.

### `knowledge/queries/*.sql` — validated example queries

```sql
-- <query label_as_identifier>
-- <description>One-sentence summary shown in knowledge search results.</description>
-- <parameters>
--   param_name: meaning (default value)
-- </parameters>
-- <notes>
--   Why this query is the canonical pattern. What it filters out.
-- </notes>
-- <query>
SELECT ...
-- </query>
```

Keep the SQL under ~25 lines. Parameterize the fiddly bits. Always filter to "completed" data if the domain has open/cancelled rows.

### `knowledge/business/*.md` — free-form markdown

Read verbatim by `search_knowledge`. One file per topic is fine, one file for everything is also fine. Minimum sections worth including: canonical metric definitions, time-filtering rules, string-column gotchas (TRIM, UPPER), forbidden columns/tables.

## Loading & reloading

After editing **any** file under `knowledge/`:

```bash
uv run python scripts/load_knowledge.py             # upsert (skip existing)
uv run python scripts/load_knowledge.py --recreate  # drop and reload from scratch
```

`--recreate` is needed when:
- You change the embedder (different dimensions)
- You rename a file (old vectors stay otherwise)
- You want a clean baseline for debugging

## Verifying

```bash
# How many vectors are in the store?
docker exec agentos-db psql -U ai -d ai -c "SELECT COUNT(*) FROM ibmi_knowledge;"

# What does the agent retrieve for a query?
uv run python cli.py --agent text2sql --prompt "What's in QSYS2.SYSTABLES?"
# Check the trace — search_knowledge results should appear before the SQL is composed
```

## Attaching to a new agent

```python
from app.knowledge import ibmi_knowledge

your_agent = Agent(
    # ...
    knowledge=ibmi_knowledge,
    search_knowledge=True,
    # ...
)
```

`search_knowledge=True` makes Agno call `knowledge.search()` automatically when relevant; if you'd rather call it explicitly from the agent's prompt, leave it off and add a `search_knowledge` tool. The template uses the implicit path because retrieval-on-every-turn is the dash pattern's whole point.

## Per-agent or per-domain knowledge

The template ships **one** shared knowledge base for simplicity — every agent searches the same `ibmi_knowledge` table. If you want per-domain isolation (e.g. one knowledge per IBM i system), build a second instance:

```python
# app/knowledge.py
finance_knowledge = create_knowledge(name="Finance KB", table_name="finance_knowledge")
```

…and load it from a different directory by adapting `scripts/load_knowledge.py`. The dash template extends this further with per-domain `DashDomainConfig` factories — out of scope for this starter, but easy to grow into.

## Costs / latency

- **Embedding** runs at file-ingest time. On the default Ollama model (Qwen3-Embedding-0.6B, 1024 dims, CPU on a laptop), all seed files load in <10s. Bigger knowledge bases benefit from a GPU.
- **Search** runs on every agent turn when `search_knowledge=True`. PgVector's hybrid search (BM25 + cosine) is fast — typically <50 ms for the seed corpus. Watch the trace if it becomes noticeable.
- **Storage**: ~4 KB per chunk in the contents table + the vector itself. Seed corpus fits in <1 MB.
