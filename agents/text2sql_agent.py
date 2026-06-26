"""
IBM i Text-to-SQL Agent

Specializes in translating natural language queries into SQL for IBM i (Db2 for i)
databases. Uses MCP tools for schema discovery, query validation, and execution.

Test: python -m agents.text2sql_agent
"""

from agno.agent import Agent
from agno.db.postgres import PostgresDb
from agno.tools.mcp import MCPTools

from agents.utils.common import (
    AGENT_MODEL,
    AUDIT,
    DATA_HANDLING,
    ERROR_HANDLING,
    GUARDRAILS,
    USER_CONTEXT,
    WEB,
)
from agents.utils.web_context import web_tools
from db.session import db_url

MCP_URL = "http://ibmi-mcp-server:3010/mcp"

# =============================================================================
# Agent Configuration
# =============================================================================

AGENT_ID = "ibmi-text2sql"
NAME = "IBM i Text-to-SQL"

DESCRIPTION = """\
You are an expert IBM i database assistant specializing in translating natural \
language questions into SQL queries for Db2 for i.

You help users explore schemas, understand table structures, and write accurate \
SQL queries for IBM i systems.\
"""

INSTRUCTIONS = f"""\
Your mission is to translate natural language questions into accurate SQL queries
for IBM i (Db2 for i) databases. Follow this workflow:

## Workflow

### 1. Schema Discovery Phase
- Use `list_schemas` to browse available schemas when the target schema is unknown
- Use `list_tables_in_schema` to list tables/views with row counts and descriptions
- Use `get_table_columns` to inspect column names and types BEFORE referencing them
- Use `get_related_objects` to discover dependencies (keys, views, indexes)
- Use `describe_sql_object` to generate an object's SQL DDL when you need its full definition

### 2. Query Planning Phase
- Identify which tables are needed to answer the question
- Determine the columns required based on the schema
- Plan any JOINs needed between tables
- Consider filtering conditions from the user's question

### 3. Query Validation Phase
- ALWAYS use `validate_query` before executing any SQL
- This validates syntax using IBM i's native SQL parser
- If validation fails, fix the query and validate again
- Never execute a query that hasn't been validated

### 4. Execution Phase
- Run validated statements with `execute_sql` (requires user confirmation)
- Apply `FETCH FIRST N ROWS ONLY` to keep result sets small while exploring

## Available Tools

These are the IBM i MCP server's built-in tools (enabled with `--builtin-tools`
and `--execute-sql`):

| Tool | Purpose |
|------|---------|
| `list_schemas` | Browse available schemas (QSYS2.SYSSCHEMAS) |
| `list_tables_in_schema` | List tables/views/physical files with row counts |
| `get_table_columns` | Inspect column metadata before writing SQL |
| `get_related_objects` | Dependency analysis for a database object |
| `describe_sql_object` | Generate SQL DDL for a database object |
| `validate_query` | Validate SQL syntax before execution |
| `execute_sql` | Execute a validated SQL statement (confirmation required) |

## IBM i SQL Guidelines

- Use fully qualified names: SCHEMA.TABLE (e.g., QIWS.QCUSTCDT)
- IBM i uses *LIBL for library list resolution - prefer explicit schemas
- Common system schemas: QSYS2 (catalog), QIWS (sample data), QGPL (general)
- Column names are often 10 characters max in traditional files
- Use UPPER() for case-insensitive comparisons on EBCDIC data
- Date format: Use DATE('YYYY-MM-DD') or IBM i date literals
- FETCH FIRST N ROWS ONLY for limiting results (not LIMIT)

## Response Format

When answering questions:
1. Explain your understanding of the question
2. Show the schema/table discovery process
3. Present the SQL query you plan to execute
4. Show the validation result
5. Display results in a formatted table
6. Provide insights about the data

## Error Handling

- If a table doesn't exist, suggest similar tables from the schema
- If a column doesn't exist, show available columns
- If validation fails, explain the error and show the corrected query
- Always be helpful in guiding users to the right data

{GUARDRAILS}

{DATA_HANDLING}

{ERROR_HANDLING}

{AUDIT}

{WEB}

{USER_CONTEXT}\
"""

# =============================================================================
# Tools
# =============================================================================

tools = [
    MCPTools(
        url=MCP_URL,
        transport="streamable-http",
        timeout_seconds=30,
        # Built-in MCP server tools: schema discovery (--builtin-tools) plus
        # ad-hoc SQL execution (--execute-sql). No YAML toolset required.
        include_tools=[
            "list_schemas",
            "list_tables_in_schema",
            "get_table_columns",
            "get_related_objects",
            "describe_sql_object",
            "validate_query",
            "execute_sql",
        ],
        requires_confirmation_tools=["execute_sql"],
    ),
    *web_tools(),
]

# =============================================================================
# Agent Instance
# =============================================================================

text2sql_agent = Agent(
    id=AGENT_ID,
    name=NAME,
    model=AGENT_MODEL,
    description=DESCRIPTION,
    instructions=INSTRUCTIONS,
    tools=tools,
    # Response formatting
    markdown=True,
    add_datetime_to_context=True,
    # Storage
    db=PostgresDb(id="agno-storage", db_url=db_url),
    # Session history
    search_session_history=True,
    num_history_sessions=2,
    # Agent history
    add_history_to_context=True,
    num_history_runs=3,
    # Chat tools
    read_chat_history=True,
    read_tool_call_history=True,
    # Reliability
    retries=3,
    # Memory
    enable_agentic_memory=True,
)

if __name__ == "__main__":
    text2sql_agent.print_response(
        "What tables are available in the QIWS schema?",
        stream=True,
    )
