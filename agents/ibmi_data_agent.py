"""
IBM i Data Agent

Read-only Q&A over the Db2 for i SAMPLE library — schema discovery and
employee/department/project lookups via the ``sample_data`` toolset
served by ibmi-mcp-server.

Toolset (from tools/sample.yaml):
  - sample_data — schema-discovery + employee-info tools scoped to SAMPLE
"""

from __future__ import annotations

from agno.agent import Agent

from agents import AGENT_DEFAULTS
from agents.utils.common import (
    DOMAIN_RULES,
    FORMATTING,
    GUARDRAILS,
    SQL_POLICY,
    build_instructions,
)
from agents.utils.toolsets import ibmi_tools
from app.knowledge import ibmi_knowledge
from app.settings import default_model
from db import get_postgres_db

# =============================================================================
# Agent Configuration
# =============================================================================

AGENT_ID = "ibmi-data-agent"
NAME = "IBM i Data Agent"

DESCRIPTION = """\
Read-only Q&A over the Db2 for i SAMPLE library — employees, departments, \
projects, and activities. Uses schema-discovery and employee-info tools \
scoped to SAMPLE.\
"""

# =============================================================================
# Tools — sample_data toolset (schema discovery + employee info)
# =============================================================================

tools = [ibmi_tools("sample_data")]

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

ibmi_data_agent = Agent(
    id=AGENT_ID,
    name=NAME,
    model=default_model(),
    description=DESCRIPTION,
    instructions=INSTRUCTIONS,
    tools=tools,
    db=get_postgres_db(),
    knowledge=ibmi_knowledge,
    search_knowledge=True,
    **AGENT_DEFAULTS,
)
