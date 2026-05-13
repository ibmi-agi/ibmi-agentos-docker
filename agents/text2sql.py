"""
IBM i Text-to-SQL Agent

Translates natural language questions into Db2 for i SQL queries — schema
exploration, query generation, validation, and execution against IBM i
systems. The go-to agent for ad-hoc SQL work.

Tools (built-in to ibmi-mcp-server when IBMI_ENABLE_DEFAULT_TOOLS=true):
  - execute_sql, validate_query, describe_sql_object
  - list_schemas, list_tables_in_schema, get_table_columns, get_related_objects

Web research is wired through ``agents.utils.web_context`` — Parallel.ai
MCP behind a synthesizing sub-agent so the main agent never sees raw
search snippets in its context window.
"""

from __future__ import annotations

from agno.agent import Agent

from agents import AGENT_DEFAULTS
from agents.config import SQL_CONFIRMATION_TOOLS, SQL_TOOLS
from agents.utils.common import (
    DOMAIN_RULES,
    FORMATTING,
    GUARDRAILS,
    SQL_POLICY,
    WEB,
    build_instructions,
)
from agents.utils.toolsets import collect_tools, ibmi_tools
from agents.utils.web_context import web_tools
from app.knowledge import ibmi_knowledge
from app.settings import default_model
from db import get_postgres_db
from learning import get_learning

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
# Tools — built-in SQL tools + web research sub-agent
# =============================================================================

tools = collect_tools(
    ibmi_tools(
        include_tools=SQL_TOOLS,
        requires_confirmation_tools=SQL_CONFIRMATION_TOOLS,
    ),
    *web_tools(),
)

# =============================================================================
# Instructions
# =============================================================================

INSTRUCTIONS = build_instructions(
    GUARDRAILS,
    DOMAIN_RULES,
    SQL_POLICY,
    WEB,
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
    knowledge=ibmi_knowledge,
    search_knowledge=True,
    learning=get_learning(),
    **AGENT_DEFAULTS,
)
