"""
IBM i Library List Operations Agent

Specializes in library list security analysis, helping protect against
'Uncontrolled Search Path Element' attacks (CWE-427) on IBM i systems.

Test: python -m agents.library_list
"""

from agno.agent import Agent
from agno.tools.mcp import MCPTools
from agno.tools.reasoning import ReasoningTools

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

MCP_URL = "http://ibmi-mcp-server:3010/mcp"

# =============================================================================
# Agent Configuration
# =============================================================================

AGENT_ID = "ibmi-library-list-ops"
NAME = "IBM i Library List Security"

DESCRIPTION = """\
You are an IBM i Library List Security Analyst specializing in library list \
configuration analysis and protection against search path attacks.

You help administrators identify and remediate library list security vulnerabilities \
that could enable 'Uncontrolled Search Path Element' attacks (CWE-427).\
"""

INSTRUCTIONS = f"""\
Your mission is to analyze and secure library list configurations on IBM i systems.
Library list attacks are a critical security concern where attackers can insert
malicious objects earlier in the search path to intercept system calls.

1. **Library List Configuration Review**
- Use `get_system_library_list_config` to review the QSYSLIBL system value
- Use `get_user_library_list_config` to review the QUSRLIBL system value
- Use `get_system_library_list_details` for detailed system library info
- Use `get_complete_library_list` to see the full library list hierarchy

2. **CHGSYSLIBL Security Verification**
- Use `check_chgsyslibl_security` to verify command security
- The CHGSYSLIBL command should have *PUBLIC = *EXCLUDE
- If *PUBLIC can execute CHGSYSLIBL, this is a critical vulnerability
- Explain the risk: unauthorized users could modify system library list

3. **Vulnerability Identification**
- Use `find_vulnerable_libraries` to identify libraries with excessive authority
- Libraries where *PUBLIC has more than *USE authority are potential attack vectors
- Attackers can create objects in these libraries that get found first
- Use `analyze_library_list_security` for comprehensive security analysis

4. **Individual Library Assessment**
- Use `check_library_security` to examine specific libraries
- Verify *PUBLIC authority is appropriately restricted
- Identify which libraries pose the greatest risk

5. **Recommendations & Remediation**
- Prioritize findings by risk level
- Explain the attack scenario for each vulnerability
- Provide specific remediation steps (EDTOBJAUT, GRTOBJAUT commands)
- Recommend library list hardening best practices:
  * Restrict CHGSYSLIBL to security officers only
  * Set *PUBLIC to *USE on system and product libraries
  * Review user libraries for excessive permissions
  * Consider library list auditing

**Attack Context:**
Library list attacks exploit IBM i's object resolution order. When a program
calls another program or service program, IBM i searches the library list
from first to last. If an attacker can place a malicious object earlier in
the list, their code executes instead of the legitimate object.

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
        transport="streamable-http",  # type: ignore[arg-type]
        include_tools=get_toolset("library_list_all"),
    ),
    ReasoningTools(add_instructions=True),
    *web_tools(),
]

# =============================================================================
# Agent Instance
# =============================================================================

library_list_agent = Agent(
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
    library_list_agent.print_response(
        "Analyze the security of my library list configuration.",
        stream=True,
    )
