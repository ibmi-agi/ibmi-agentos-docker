"""
AgentOS Entrypoint
==================

Three IBM i agents are registered out of the box. Add yours by importing
it here and appending to the ``agents=[]`` list — see ``docs/create-new-agent.md``.

When ``AUTH_ENABLED=true`` the optional auth middleware is attached
(see ``docs/auth-optional.md``).
"""

from contextlib import asynccontextmanager
from os import getenv
from pathlib import Path

from agno.os import AgentOS
from agno.utils.log import log_info

from agents.sql_service_guide import sql_service_guide_agent
from agents.system_health import system_health_agent
from agents.text2sql import text2sql_agent
from agents.utils.web_context import web_backend
from db import get_postgres_db

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
runtime_env = getenv("RUNTIME_ENV", "prd")
scheduler_base_url = getenv("AGENTOS_URL", "http://127.0.0.1:8000")
auth_enabled = getenv("AUTH_ENABLED", "false").lower() in ("true", "1", "yes")


# ---------------------------------------------------------------------------
# Lifespan — sets up shared context backends (web research) for the
# duration of the app process. AgentOS handles the MCP tool lifecycle
# (connect on startup, close on shutdown) on top of this hook.
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
    scheduler=True,
    scheduler_base_url=scheduler_base_url,
    authorization=runtime_env == "prd",
    lifespan=lifespan,
    db=get_postgres_db(),
    agents=[
        text2sql_agent,
        sql_service_guide_agent,
        system_health_agent,
    ],
    config=str(Path(__file__).parent / "config.yaml"),
)
app = agent_os.get_app()


# ---------------------------------------------------------------------------
# Optional multi-user MCP auth — see docs/auth-optional.md
# ---------------------------------------------------------------------------
if auth_enabled:
    from auth.middleware import APIKeyAuthMiddleware

    app.add_middleware(APIKeyAuthMiddleware)
    log_info("Auth middleware enabled (AUTH_ENABLED=true)")


if __name__ == "__main__":
    agent_os.serve(app="app.main:app", reload=runtime_env == "dev")
