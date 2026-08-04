"""
AgentOS Entrypoint
==================

Registers the IBM i agents on Agno AgentOS. Add your own by importing it
here and appending to the ``agents=[]`` list — see ``docs/create-new-agent.md``.

The lifespan sets up the shared Parallel web-research backend (the
``query_web`` tool) for the duration of the app process. AgentOS manages the
MCP tool lifecycle (connect on startup, close on shutdown) on top of this hook.
"""

from contextlib import asynccontextmanager
from os import getenv
from pathlib import Path

from agno.os import AgentOS
from agno.utils.log import log_info

from agents.library_list_security_agent import library_list_agent
from agents.performance_agent import performance_agent
from agents.ptf_agent import ptf_agent
from agents.sample_data_agent import sample_agent
from agents.security_audit_agent import security_audit_agent
from agents.text2sql_agent import text2sql_agent
from agents.utils.web_context import web_backend
from db import get_postgres_db

runtime_env = getenv("RUNTIME_ENV", "prd")


# ---------------------------------------------------------------------------
# Lifespan — sets up the shared web-research backend (the ``query_web`` tool)
# for the duration of the app process.
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app):  # type: ignore[no-untyped-def]
    log_info("AgentOS lifespan: startup")
    backend = web_backend()
    await backend.asetup()
    try:
        yield
    finally:
        await backend.aclose()
        log_info("AgentOS lifespan: shutdown")


# ---------------------------------------------------------------------------
# Create AgentOS
# ---------------------------------------------------------------------------
agent_os = AgentOS(
    name="IBM i AgentOS",
    tracing=True,
    lifespan=lifespan,
    # MCP interface at /mcp (streamable HTTP, same port as the REST API) —
    # chat apps and coding agents drive the agents through it. No auth layer
    # in this template, so it shares the API's network-posture boundary.
    mcp_server=True,
    db=get_postgres_db(),
    agents=[
        text2sql_agent,
        performance_agent,
        security_audit_agent,
        library_list_agent,
        ptf_agent,
        sample_agent,
    ],
    config=str(Path(__file__).parent / "config.yaml"),
)
app = agent_os.get_app()


if __name__ == "__main__":
    agent_os.serve(app="app.main:app", reload=runtime_env == "dev")
