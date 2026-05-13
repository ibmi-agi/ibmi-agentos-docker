"""
IBM i System Health Agent

Monitors IBM i system performance and diagnoses resource issues — CPU,
memory, disk/ASP, temp storage, job counts, and collection services.
Uses curated performance and daily health toolsets for structured,
severity-rated assessments. Core SQL tools available as backup for
ad-hoc queries.

Toolsets (from tools/performance.yaml and tools/daily-health.yaml):
  - performance    (system_status, active_job_info, memory_pools, etc.)
  - daily_health   (joblog_info, system_value_lookup)

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

AGENT_ID = "ibmi-system-health"
NAME = "IBM i System Health Agent"

DESCRIPTION = """\
Monitors IBM i system performance and diagnoses resource issues — CPU, \
memory, disk/ASP, temp storage, job counts, and collection services. \
Does NOT handle security, database exploration, or PTF management.\
"""

# =============================================================================
# Tools — performance + daily_health toolsets + core SQL + web research sub-agent
# =============================================================================

tools = collect_tools(
    ibmi_tools(
        [
            "performance",
            "daily_health",
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

system_health_agent = Agent(
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
