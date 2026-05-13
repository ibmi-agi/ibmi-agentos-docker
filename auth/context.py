"""
Auth Context
============

Shared context variables and constants for the multi-user auth system.

Context variables allow the middleware to pass per-request auth state
to downstream components (e.g., MCPTools header_provider) without
threading it through function arguments.
"""

from __future__ import annotations

import contextvars
from os import getenv
from uuid import UUID

# MCP auth mode — "ibmi" enables per-user IBM i authentication
MCP_AUTH_MODE = getenv("MCP_AUTH_MODE", "none").lower()

# Per-request context: the resolved MCP Bearer token
mcp_auth_token: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "mcp_auth_token", default=None
)

# Per-request context: the resolved connection ID
mcp_connection_id: contextvars.ContextVar[UUID | None] = contextvars.ContextVar(
    "mcp_connection_id", default=None
)

# Per-request context: the authenticated API key ID (for multi-system lookups)
current_api_key_id: contextvars.ContextVar[UUID | None] = contextvars.ContextVar(
    "current_api_key_id", default=None
)
