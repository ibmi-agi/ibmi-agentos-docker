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
and Parallel.ai web research.
"""

from __future__ import annotations

from os import getenv

from agno.agent import Agent
from agno.tools.mcp import MCPTools
from agno.tools.parallel import ParallelTools

from agents import AGENT_DEFAULTS
from agents.config import CORE_SQL_TOOLS, SQL_CONFIRMATION_TOOLS
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

AGENT_ID = "ibmi-system-health"
NAME = "IBM i System Health Agent"

DESCRIPTION = """\
Monitors IBM i system performance and diagnoses resource issues — CPU, \
memory, disk/ASP, temp storage, job counts, and collection services. \
Does NOT handle security, database exploration, or PTF management.\
"""

# =============================================================================
# Tools — performance + daily_health toolsets + core SQL + Parallel.ai web research
# =============================================================================

if getenv("PARALLEL_API_KEY"):
    _web_tools: ParallelTools | MCPTools = ParallelTools()
else:
    _web_tools = MCPTools(url="https://search.parallel.ai/mcp", transport="streamable-http")

tools = collect_tools(
    ibmi_tools(
        [
            "performance",
            "daily_health",
        ],
        include_tools=CORE_SQL_TOOLS,
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

system_health_agent = Agent(
    id=AGENT_ID,
    name=NAME,
    model=default_model(),
    description=DESCRIPTION,
    instructions=INSTRUCTIONS,
    tools=tools,
    db=get_postgres_db(),
    **AGENT_DEFAULTS,
)
