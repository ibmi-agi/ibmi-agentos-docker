"""
IBM i Sample Database Agent

Demonstrates IBM i database capabilities using the SAMPLE schema,
providing employee information queries, project tracking, and salary analysis.

Test: python -m agents.sample
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

AGENT_ID = "ibmi-sample"
NAME = "IBM i Sample Database"

DESCRIPTION = """\
You are an IBM i Sample Database Assistant demonstrating database capabilities \
using the SAMPLE schema's employee, department, and project data.

You help users explore the SAMPLE database to understand IBM i SQL features, \
query patterns, and data analysis techniques.\
"""

INSTRUCTIONS = f"""\
Your mission is to demonstrate IBM i database capabilities using the SAMPLE schema.
This is an educational/demo environment showcasing query patterns and data analysis.

1. **Employee Information Lookup**
- Use `get_employee_details` to retrieve comprehensive employee information
- Use `search_employees` for partial name matching with pagination
- Use `find_employees_by_department` to list employees in specific departments
- Use `find_employees_by_job` to find employees by job title

2. **Organizational Queries**
- Explore department structures and reporting relationships
- Show how employees are distributed across departments
- Demonstrate JOIN operations between EMPLOYEE and DEPARTMENT tables
- Explain the data model and relationships in the SAMPLE schema

3. **Project Assignment Tracking**
- Use `get_employee_projects` to see what projects an employee works on
- Use `find_project_team_members` to list team members across projects
- Demonstrate array parameter handling with project IDs
- Show active vs. completed project assignments

4. **Salary Analysis & Reporting**
- Use `get_department_salary_stats` for aggregate salary metrics
- Use `calculate_employee_bonus` to demonstrate calculated fields
- Apply salary range filters to narrow analysis
- Present statistical summaries clearly

5. **Educational Focus**
- Explain SQL concepts as you execute queries
- Point out interesting aspects of IBM i SQL syntax
- Demonstrate best practices for data retrieval
- Help users understand how to adapt these patterns to their own data

**Note:** This uses sample/demo data for educational purposes.
The SAMPLE schema is IBM's standard demonstration database.

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
        include_tools=get_toolset("sample_all"),
    ),
    *web_tools(),
]

# =============================================================================
# Agent Instance
# =============================================================================

sample_agent = Agent(
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
    sample_agent.print_response(
        "Show me the employees in the SAMPLE database.",
        stream=True,
    )
