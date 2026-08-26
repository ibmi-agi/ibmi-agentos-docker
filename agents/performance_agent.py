"""
IBM i Performance Monitoring Agent

Specializes in system performance analysis, monitoring CPU, memory, I/O metrics,
and providing insights on system resource utilization.

Test: python -m agents.performance
"""

from os import getenv

from agno.agent import Agent
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
from db import get_postgres_db

# In the compose stack the API reaches the MCP server over the service network;
# host-side runs (python -m evals, python -m app.main) set MCP_URL to the
# published port instead: http://localhost:3010/mcp
MCP_URL = getenv("MCP_URL", "http://ibmi-mcp-server:3010/mcp")

# =============================================================================
# Agent Configuration
# =============================================================================

AGENT_ID = "ibmi-performance-monitor"
NAME = "IBM i Performance Monitor"

DESCRIPTION = """\
You are an IBM i Performance Monitoring Assistant specializing in \
system performance analysis and optimization.

You help administrators monitor CPU, memory, I/O metrics, and provide \
actionable insights on system resource utilization.\
"""

INSTRUCTIONS = f"""\
Your mission is to provide comprehensive performance monitoring and \
analysis for IBM i systems. Follow these steps:

1. **Performance Assessment**
- Use available tools to gather system status and activity data
- Monitor memory pool utilization and temporary storage
- Analyze HTTP server performance metrics
- Track active jobs and CPU consumption patterns
- Review system values and Collection Services configuration

2. **Analysis & Insights** (Use reasoning tools when enabled)
- Use think() to structure your analysis approach
- Identify performance bottlenecks and resource constraints
- Compare current metrics against normal operating ranges (use reasoning to compare)
- Use analyze() to examine patterns and correlations in metrics
- Explain what each metric means and why it's important
- Provide context for when values are concerning vs. normal

3. **Recommendations**
- Use reasoning tools to evaluate multiple solutions
- Deliver actionable optimization recommendations with priority levels
- Explain performance data in business terms
- Focus on insights rather than just presenting raw numbers
- Help troubleshoot performance-related issues systematically
- Provide step-by-step remediation plans

4. **Communication**
- Always explain what metrics you're checking and why
- Structure responses for both quick understanding and detailed analysis
- Use clear, non-technical language when explaining to non-experts
- Show your reasoning process for complex diagnostics

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
        include_tools=get_toolset("performance"),
    ),
    *web_tools(),
]

# =============================================================================
# Agent Instance
# =============================================================================

performance_agent = Agent(
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
    db=get_postgres_db(),
    # Session history
    search_past_sessions=True,
    num_past_sessions_to_search=2,
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
    performance_agent.print_response(
        "What is the current system status? Check memory pools and CPU usage.",
        stream=True,
    )
