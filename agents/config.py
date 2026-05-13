"""Project-wide constants for IBM i agents.

Minimal config — just the things every agent needs:
    * The MCP server URL (where ``ibmi-mcp-server`` is reachable)
    * Curated SQL tool name lists

Model resolution lives in ``app/settings.py::default_model()``.
"""

from __future__ import annotations

from os import getenv
from pathlib import Path

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

# ---------------------------------------------------------------------------
# IBM i CLI (offline / no-MCP mode)
# ---------------------------------------------------------------------------
# When ``IBMI_CLI_MODE=true``, agents talk to the local ``ibmi`` binary via
# IBMiCLITools instead of connecting to ibmi-mcp-server. The binary is baked
# into the container image (see Dockerfile multi-stage build). Read at import
# time — flipping requires a container restart.
CLI_MODE = getenv("IBMI_CLI_MODE", "false").lower() in ("true", "1", "yes")

# Path to the bundled ``ibmi`` CLI binary. Defaults to the name on PATH.
IBMI_CLI = getenv("IBMI_CLI", "ibmi")

# Subprocess timeout for CLI dispatch (seconds).
IBMI_CLI_TIMEOUT = int(getenv("IBMI_CLI_TIMEOUT", "120"))

# Tool YAML discovery roots for the CLI toolkit's ``list_tools`` / ``run_tool``
# methods. PROJECT_TOOLS_DIR is the in-repo ``tools/`` directory; USER_TOOLS_DIR
# is an optional host-mounted directory for user-supplied YAMLs.
PROJECT_TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
USER_TOOLS_DIR = Path(getenv("IBMI_USER_TOOLS_DIR", "/data/user_tools"))
