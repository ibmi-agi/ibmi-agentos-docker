"""
IBM i Text-to-SQL Agent

Translates natural language questions into Db2 for i SQL queries — schema
exploration, query generation, validation, and execution against IBM i
systems. The go-to agent for ad-hoc SQL work.

Tools (built-in to ibmi-mcp-server when IBMI_ENABLE_DEFAULT_TOOLS=true):
  - execute_sql, validate_query, describe_sql_object
  - list_schemas, list_tables_in_schema, get_table_columns, get_related_objects

Optional web research is wired through Parallel.ai (PARALLEL_API_KEY or keyless).
"""

from __future__ import annotations

from os import getenv

from agno.agent import Agent
from agno.tools.mcp import MCPTools
from agno.tools.parallel import ParallelTools

from agents import AGENT_DEFAULTS
from agents.config import SQL_CONFIRMATION_TOOLS, SQL_TOOLS
from agents.utils.common import (
    DOMAIN_RULES,
    FORMATTING,
    GUARDRAILS,
    SQL_POLICY,
    build_instructions,
)
from agents.utils.toolsets import collect_tools, ibmi_tools
from app.settings import default_model
from db import get_postgres_db

# =============================================================================
# Agent Configuration
# =============================================================================

AGENT_ID = "ibmi-text2sql"
NAME = "IBM i Text-to-SQL Agent"

DESCRIPTION = """\
Translates natural language questions into Db2 for i SQL queries — schema \
exploration, query generation, validation, and execution against IBM i \
systems. The go-to agent for ad-hoc SQL work.\
"""

# =============================================================================
# Tools — SQL tools (built-in MCP) + Parallel.ai web research (optional)
# =============================================================================

if getenv("PARALLEL_API_KEY"):
    _web_tools: ParallelTools | MCPTools = ParallelTools()
else:
    _web_tools = MCPTools(url="https://search.parallel.ai/mcp", transport="streamable-http")

tools = collect_tools(
    ibmi_tools(
        include_tools=SQL_TOOLS,
        requires_confirmation_tools=SQL_CONFIRMATION_TOOLS,
    ),
    _web_tools,
)

# =============================================================================
# Instructions
# =============================================================================

INSTRUCTIONS = build_instructions(
    GUARDRAILS,
    DOMAIN_RULES,
    SQL_POLICY,
    FORMATTING,
    agent_id=AGENT_ID,
)

# =============================================================================
# Agent
# =============================================================================

text2sql_agent = Agent(
    id=AGENT_ID,
    name=NAME,
    model=default_model(),
    description=DESCRIPTION,
    instructions=INSTRUCTIONS,
    tools=tools,
    db=get_postgres_db(),
    **AGENT_DEFAULTS,
)
