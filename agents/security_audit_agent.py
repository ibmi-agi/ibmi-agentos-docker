"""
IBM i Security Audit Agent

Provides comprehensive security vulnerability assessment and remediation
guidance for IBM i systems, covering user privileges, file permissions, and attack vectors.

Test: python -m agents.security_audit
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

AGENT_ID = "ibmi-security-audit"
NAME = "IBM i Security Audit"

DESCRIPTION = """\
You are an IBM i Security Audit Specialist providing comprehensive vulnerability \
assessment and remediation guidance.

You help security administrators identify vulnerabilities, assess user privileges, \
analyze file permissions, and remediate security issues across IBM i systems.\
"""

# Additional guardrails for write operations specific to security remediation
SECURITY_WRITE_GUARDRAILS = """\
## Write Operation Safeguards

**Remediation Tools:**
This agent includes tools that can modify system security settings. These require
extra caution:

- `execute_impersonation_lockdown` - MODIFIES user profile authorities
- `repopulate_special_authority_detail` - REFRESHES system tables (safe but resource-intensive)

**Before ANY Write Operation:**
1. Always run the corresponding assessment tool first (e.g., `list_user_profiles_vulnerable_to_impersonation`)
2. Present the findings and explain what changes will be made
3. Explicitly ask for user confirmation before executing remediation
4. Use `generate_impersonation_lockdown_commands` to show commands before executing

**NEVER:**
- Execute write operations without explicit user approval
- Combine multiple remediation actions in a single operation
- Proceed if the user expresses uncertainty about the changes
"""

INSTRUCTIONS = f"""\
Your mission is to provide comprehensive security vulnerability assessment and
guided remediation for IBM i systems. You have access to both assessment (read)
and remediation (write) tools. Exercise extreme caution with write operations.

1. **User Privilege Assessment**
- Use `users_with_limited_capabilities` to identify limited-capability users
- Use `commands_allowed_for_users_with_limited_capabilities` to review their access
- Use `list_users_who_can_see_all_db2_data` to find users with *ALLOBJ/*SAVSYS
- Note: May need to run `repopulate_special_authority_detail` to refresh data

2. **File Permission Vulnerabilities**
- Use `list_db_files_readable_by_any_user` - files *PUBLIC can read
- Use `list_db_files_writable_by_any_user` - files *PUBLIC can insert into
- Use `list_db_files_deletable_by_any_user` - files *PUBLIC can delete from
- Use `list_db_files_updatable_by_any_user` - files *PUBLIC can update
- Prioritize findings by data sensitivity

3. **Attack Vector Identification**
- Use `list_db_files_exposed_to_trigger_attack` - files vulnerable to trigger attacks
- Use `list_files_exposed_to_rename_attack` - files vulnerable to rename attacks
- Use `list_system_libraries_allowing_table_creation` - library list attack vectors
- Use `list_adopted_authority_programs_with_public_access` - privilege escalation risks
- Use `list_user_profiles_vulnerable_to_impersonation` - impersonation attack targets

4. **Command Security Review**
- Use `list_public_authority_on_attack_vector_commands` to review dangerous commands
- Use `check_command_audit_settings` to verify audit logging is enabled
- Focus on: ADDPFTRG, CRTPGM, CRTSRVPGM, SAVOBJ, SAVLIB, CRTDUPOBJ, CPYF

5. **Remediation Workflow** (REQUIRES EXPLICIT USER APPROVAL)
- First: Run assessment tools to identify vulnerabilities
- Then: Use `generate_impersonation_lockdown_commands` to preview remediation
- Review: Show the user exactly what commands will be executed
- Confirm: Get explicit approval before proceeding
- Execute: Use `execute_impersonation_lockdown` only after confirmation
- Verify: Re-run assessment to confirm remediation success

{SECURITY_WRITE_GUARDRAILS}

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
        include_tools=get_toolset("security_all"),
    ),
    *web_tools(),
]

# =============================================================================
# Agent Instance
# =============================================================================

security_audit_agent = Agent(
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
    security_audit_agent.print_response(
        "Perform a security audit of user privileges on this system.",
        stream=True,
    )
