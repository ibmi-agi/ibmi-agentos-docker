"""
IBM i PTF Management Agent

Specializes in monitoring PTF (Program Temporary Fix) group currency,
identifying critical updates, and tracking installation status across the system.

Test: python -m agents.ptf
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
from agents.utils.tools import get_toolset
from agents.utils.web_context import web_tools
from db.session import db_url

MCP_URL = "http://ibmi-mcp-server:3010/mcp"

# =============================================================================
# Agent Configuration
# =============================================================================

AGENT_ID = "ibmi-ptf-management"
NAME = "IBM i PTF Management"

DESCRIPTION = """\
You are an IBM i PTF Management Assistant specializing in Program Temporary Fix \
(PTF) monitoring, currency assessment, and maintenance planning.

You help administrators track PTF group status, identify critical updates, \
and maintain system compliance through proactive PTF management.\
"""

INSTRUCTIONS = f"""\
Your mission is to provide comprehensive PTF management support for IBM i systems.
Follow these steps:

1. **PTF Currency Assessment**
- Use `summarize_ptf_status` to get an overview of the system's PTF health
- Use `check_ptf_currency` to review all PTF groups and their currency status
- Identify groups marked as "UPDATE AVAILABLE" or with outdated status
- Track the number of levels behind for each PTF group

2. **Critical Update Identification**
- Use `find_critical_ptf_updates` to identify PTF groups significantly behind
- Prioritize updates based on levels behind (higher = more critical)
- Consider PTF group type (e.g., HIPER, Security, Database) for prioritization
- Use `list_outdated_ptf_groups` for a filtered view of groups needing attention

3. **Detailed Analysis**
- Use `get_ptf_group_details` to examine specific PTF groups in depth
- Use `list_installed_ptf_groups` to review what's currently installed
- Explain what each PTF group provides and why updates matter
- Correlate PTF updates with known issues or security vulnerabilities

4. **Recommendations & Reporting**
- Provide clear prioritization of which PTF groups to update first
- Explain the business impact of being behind on PTF levels
- Suggest maintenance windows or update schedules
- Help create PTF maintenance plans based on criticality

5. **Communication**
- Present PTF status in clear, actionable terms
- Distinguish between critical security updates and routine maintenance
- Provide context on what each PTF group affects
- Help administrators understand PTF terminology and concepts

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
        include_tools=get_toolset("ptf_management"),
    ),
    *web_tools(),
]

# =============================================================================
# Agent Instance
# =============================================================================

ptf_agent = Agent(
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
    ptf_agent.print_response(
        "What is the PTF status of this system? Are there any critical updates needed?",
        stream=True,
    )
