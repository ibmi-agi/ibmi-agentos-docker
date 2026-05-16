# Extend the Knowledge Base

> Claude Code prompt. Open Claude Code in this repo and paste:
> `Run docs/extend-knowledge.md`

You are adding a new entry to the shared knowledge base — almost always a SAMPLE table the agent should know about, but the same loop applies to business rules and example queries. The end product is a JSON / SQL / Markdown file under `knowledge/` plus a reload step that ingests it into PgVector.

The `ibmi` CLI is the only database utility you use here — it gives you the exact column names and types the JSON file should record. Background: [`docs/ibmi-cli.md`](ibmi-cli.md). Knowledge-base shape and ingestion mechanics: [`docs/knowledge-base.md`](knowledge-base.md).

## 0. Preconditions

- `.env` populated and `ibmi sql "VALUES CURRENT_DATE"` returns today's date (see [`docs/ibmi-cli.md`](ibmi-cli.md)).
- Stack healthy:

  ```bash
  docker compose up -d --build
  until curl -sSf http://localhost:8000/healthz > /dev/null; do sleep 0.5; done
  ```

- Knowledge files already loaded once (so you have a baseline to compare against):

  ```bash
  uv run python scripts/load_knowledge.py
  ```

## 1. Pick what to capture

The knowledge base has three buckets — pick the one that fits what you're adding:

| Bucket | Path | Use for |
| --- | --- | --- |
| Table metadata | `knowledge/tables/<name>.json` | One file per SAMPLE table the agent should know about |
| Business rules | `knowledge/business/sample.json` (extend) or a new file | Metric definitions, gotchas, naming conventions |
| Example queries | `knowledge/queries/sample_queries.sql` (extend) | Reusable, header-tagged SQL the agent can borrow |

This doc walks through the table case — the most common one. The other two are simpler: edit the file, save, run the reload (step 4).

## 2. Explore the table with `ibmi`

Capture the **exact** column names and types — don't transcribe from memory or guess:

```bash
# Confirm the table exists in SAMPLE
ibmi tables SAMPLE

# Get column metadata (name, type, nullable, length, default)
ibmi columns SAMPLE PROJECT

# Get the DDL for a deeper look (constraints, defaults, indexes)
ibmi describe "SAMPLE.PROJECT"

# Pull a small sample to learn what real rows look like
ibmi sql "SELECT * FROM SAMPLE.PROJECT FETCH FIRST 5 ROWS ONLY"
```

While you're here, write down anything that will trip the agent up: nullable columns it should not assume populated, CHAR-vs-VARCHAR pitfalls (trailing spaces), foreign-key relationships, status codes the agent should filter on.

## 3. Write the JSON

Create `knowledge/tables/project.json` (one table per file, lowercase name). The dash-style KB shape — what every table file in `knowledge/tables/` must use — has four required top-level keys: `table_name`, `table_description`, `use_cases`, `table_columns`. `data_quality_notes` is strongly recommended.

```json
{
  "table_name": "PROJECT",
  "schema": "SAMPLE",
  "table_description": "Projects in the SAMPLE company: project number, name, dates, sponsoring department, and responsible employee. Each project is owned by exactly one department.",
  "use_cases": [
    "Find which projects a department is running",
    "Identify the responsible employee for a project",
    "Compute project duration from PRSTDATE and PRENDATE"
  ],
  "data_quality_notes": [
    "PROJNO is the primary key (CHAR(6))",
    "DEPTNO is a foreign key to DEPARTMENT.DEPTNO — both CHAR(3)",
    "RESPEMP is a foreign key to EMPLOYEE.EMPNO — both CHAR(6)",
    "PRSTDATE / PRENDATE are DATE; PRENDATE is NULL for active projects",
    "MAJPROJ is the parent project number; NULL means top-level"
  ],
  "table_columns": [
    {"name": "PROJNO", "type": "CHAR(6)", "description": "Project number, primary key", "nullable": false},
    {"name": "PROJNAME", "type": "VARCHAR(24)", "description": "Project name", "nullable": false},
    {"name": "DEPTNO", "type": "CHAR(3)", "description": "Sponsoring department (FK to DEPARTMENT)", "nullable": false},
    {"name": "RESPEMP", "type": "CHAR(6)", "description": "Responsible employee (FK to EMPLOYEE)", "nullable": false},
    {"name": "PRSTAFF", "type": "DECIMAL(5,2)", "description": "Estimated mean staff size", "nullable": true},
    {"name": "PRSTDATE", "type": "DATE", "description": "Project start date", "nullable": true},
    {"name": "PRENDATE", "type": "DATE", "description": "Project end date; NULL means active", "nullable": true},
    {"name": "MAJPROJ", "type": "CHAR(6)", "description": "Parent project number; NULL for top-level", "nullable": true}
  ]
}
```

Write `description` strings the way you would write a SQL review comment — short, specific, copy-pasteable. "Project number, primary key" beats "The PROJNO field."

For business rules, the shape in `knowledge/business/sample.json` is documented in [`docs/knowledge-base.md`](knowledge-base.md); for example queries, see the existing `knowledge/queries/sample_queries.sql` for the `-- name:` / `-- description:` / `-- parameters:` header pattern.

## 4. Reload the knowledge base

```bash
uv run python scripts/load_knowledge.py             # upsert; safe to run repeatedly
# or
uv run python scripts/load_knowledge.py --recreate  # drop and reload from scratch
```

`--recreate` is needed if you've renamed a file (old vectors stay otherwise) or changed the embedder. Plain `load_knowledge.py` is enough for new or edited files.

Verify the vectors landed — the `load_knowledge.py` script prints a per-file ingest summary at the end. The count of indexed chunks should have grown relative to the baseline you captured in step 0.

## 5. Verify the agent picks it up

Ask the agent something only the new file can answer:

```bash
curl -sS -X POST http://localhost:8000/agents/ibmi-data-agent/runs \
  -F "message=Describe the PROJECT table in SAMPLE — what's MAJPROJ for?" \
  -F "user_id=claude-extend-knowledge" \
  -F "stream=false" \
  -o /tmp/kb-out.json \
  -w "HTTP %{http_code} in %{time_total}s\n"

jq -r '.content // .' < /tmp/kb-out.json
```

The response should reference the description / `data_quality_notes` you wrote — that's the signal `search_knowledge` retrieved your file before the model composed its answer. Check the container logs to confirm:

```bash
docker logs agentos-api --since 30s 2>&1 | grep -E "search_knowledge|knowledge" | head -20
```

If the agent doesn't surface the new content, the most common cause is the file's `table_description` being too vague — the embedder needs concrete nouns to retrieve on. Sharpen the description and re-run `scripts/load_knowledge.py`.

## 6. Commit

```bash
git status     # knowledge/tables/project.json (or whichever bucket)
git add knowledge/
git commit -m "knowledge: document SAMPLE.PROJECT for the data agent"
```

Loop back to step 1 for the next entry. The knowledge base scales linearly — one file per table, one paragraph per business rule, one validated query per `<query>` block.
