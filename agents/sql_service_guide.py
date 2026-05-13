"""
IBM i SQL Service Guide

Helps users discover and learn IBM i SQL Services — browse by category, search
by name, view examples, and explore by schema or type. Core SQL tools
available as backup for ad-hoc queries.

Toolsets (from tools/sys-admin.yaml):
  - sysadmin_discovery  (service categories, schema counts)
  - sysadmin_browse     (browse by category, schema, SQL object type)
  - sysadmin_search     (search by name, get examples, locate services)

Plus the core SQL tools (execute_sql, validate_query, describe_sql_object)
and web research via the ``agents.utils.web_context`` ContextProvider.
"""

from __future__ import annotations

from agno.agent import Agent

from agents import AGENT_DEFAULTS
from agents.config import CORE_SQL_TOOLS, SQL_CONFIRMATION_TOOLS
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
from app.settings import default_model
from db import get_postgres_db
from learning import get_learning

# =============================================================================
# Agent Configuration
# =============================================================================

AGENT_ID = "ibmi-sql-service-guide"
NAME = "IBM i SQL Service Guide"

DESCRIPTION = """\
Helps users discover and learn IBM i SQL Services — browse by category, \
search by name, view examples, and explore by schema or type. Does NOT \
execute SQL Services; it teaches users about them.\
"""

# =============================================================================
# Tools — sysadmin toolsets + core SQL + web research sub-agent
# =============================================================================

tools = collect_tools(
    ibmi_tools(
        [
            "sysadmin_discovery",
            "sysadmin_browse",
            "sysadmin_search",
        ],
        include_tools=CORE_SQL_TOOLS,
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

sql_service_guide_agent = Agent(
    id=AGENT_ID,
    name=NAME,
    model=default_model(),
    description=DESCRIPTION,
    instructions=INSTRUCTIONS,
    tools=tools,
    db=get_postgres_db(),
    learning=get_learning(),
    **AGENT_DEFAULTS,
)
