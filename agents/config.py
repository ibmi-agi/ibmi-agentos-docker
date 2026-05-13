"""Project-wide constants for IBM i agents.

Minimal config — just the things every agent needs:
    * The MCP server URL (where ``ibmi-mcp-server`` is reachable)
    * Curated SQL tool name lists

Model resolution lives in ``app/settings.py::default_model()``.
"""

from __future__ import annotations

from os import getenv

# ---------------------------------------------------------------------------
# IBM i MCP server URL
# ---------------------------------------------------------------------------
# In docker compose: http://ibmi-mcp-server:3010/mcp (the default).
# When running cli.py from the host, it overrides this to localhost:3010.
MCP_URL = getenv("MCP_URL", "http://ibmi-mcp-server:3010/mcp")

# Base URL (no /mcp suffix) — used by the optional auth/ module to fetch
# the MCP server's public key for credential wrapping. Defaults are
# aligned with MCP_URL.
MCP_UPSTREAM_URL = getenv("MCP_UPSTREAM_URL", "http://ibmi-mcp-server:3010")

# ---------------------------------------------------------------------------
# SQL tool lists (built into ibmi-mcp-server when IBMI_ENABLE_DEFAULT_TOOLS=true)
# ---------------------------------------------------------------------------

CORE_SQL_TOOLS = [
    "describe_sql_object",
    "validate_query",
    "execute_sql",
]

SQL_TOOLS = [
    *CORE_SQL_TOOLS,
    "list_schemas",
    "list_tables_in_schema",
    "get_table_columns",
    "get_related_objects",
]

# Tools that should require user confirmation before they fire.
SQL_CONFIRMATION_TOOLS = ["execute_sql"]
