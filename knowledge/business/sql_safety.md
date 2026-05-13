# SQL safety on IBM i

Habits every agent that runs SQL against an IBM i system must follow. Lifted from `agents/utils/common.py::SQL_POLICY` — repeated here so it lands in retrieval results.

## Inspect before you write

Column availability varies by Technology Refresh level. The model's training data **will** reference columns that don't exist on the target system. The cost of a wrong column name is a bad SQL execution; the cost of a `describe_sql_object` is a few hundred milliseconds. Always inspect:

1. `describe_sql_object('SCHEMA.TABLE')` (or `get_table_columns`) for every table the query touches.
2. Use **only** the column names returned by the inspection. If a column you expected isn't there, say so before guessing.

## Validate before you execute

`validate_query` runs the optimizer's parse + bind step without executing the statement. It catches syntax errors, column typos, missing tables, and permission issues before the query hits any data. Validate every non-trivial statement.

Statements you can skip validation on: single-table `SELECT ... FETCH FIRST 1 ROWS ONLY` smoke tests and other "I already know this parses" recipes.

## Present, then confirm, then execute

Destructive operations (`DELETE`, `UPDATE`, `INSERT INTO`, `DROP`, `CLEAR`, `CLRPFM`, CL commands like `RCLSTG`) require explicit user confirmation. Always:

1. Show the user the full statement.
2. State what it will change (rows affected, objects modified).
3. Wait for explicit confirmation ("yes", "run it") before calling `execute_sql`.

The MCP server's `requires_confirmation_tools` config gates this at the tool layer, but the agent's own instructions should reinforce it — defense in depth.

## Bounded result sets

- Default to 100 rows unless the user explicitly asks for more.
- Always include `FETCH FIRST N ROWS ONLY` (Db2 for i — not `LIMIT N`).
- For aggregate queries, summarize and offer the underlying detail on request rather than dumping.

## Fully qualified everything

Two-part names (`SCHEMA.TABLE`) prevent ambiguity from library-list shifts between sessions. Don't rely on `SET CURRENT SCHEMA` or `SET PATH` — explicit qualification is one extra word and zero ambiguity.

## Surface errors verbatim

When a tool call fails (auth, permission, syntax, missing table), include the actual MCP error message in the response. Don't paraphrase, don't infer the cause beyond what the error states, don't suggest fixes that aren't supported by the error text.
