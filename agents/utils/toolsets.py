"""IBM i toolset factory.

Single entry point for every agent that wants tools from the
ibmi-mcp-server. Resolves curated toolset names (defined in
``tools/*.yaml`` and compiled to ``tools/toolsets.json``) into the
underlying MCP tool name lists that AgentOS understands.

Behavior:
    Default              -> plain ``MCPTools`` against ``MCP_URL``
    AUTH_ENABLED=true +  -> ``LazyMCPTools`` with per-request bearer
    MCP_AUTH_MODE=ibmi      headers from ``auth.mcp_tokens``

The auth branch only runs when the optional ``auth/`` module is wired up
and ``AUTH_ENABLED`` is set in the environment. See ``docs/auth-optional.md``.
"""

from __future__ import annotations

from collections.abc import Callable
from os import getenv
from typing import Any, TypeAlias

from agno.tools import Toolkit
from agno.tools.function import Function
from agno.tools.mcp import MCPTools

from agents.config import MCP_URL
from agents.utils.tools import get_toolset, get_toolsets

# Union matching agno's Agent/Team ``tools`` parameter.
ToolType: TypeAlias = Toolkit | Callable[..., Any] | Function | dict[str, Any]


def collect_tools(*tools: ToolType | None) -> list[ToolType]:
    """Build a tools list, filtering out ``None`` entries from optional tools."""
    return [t for t in tools if t is not None]


def ibmi_tools(
    toolset: str | list[str] | None = None,
    *,
    url: str | None = None,
    include_tools: list[str] | None = None,
    transport: str = "streamable-http",
    timeout_seconds: int = 30,
    **kwargs: Any,
) -> MCPTools:
    """Build an agent's IBM i toolset.

    Examples:
        ibmi_tools("performance")
        ibmi_tools(["performance", "daily_health"], include_tools=["execute_sql"])
        ibmi_tools(include_tools=["execute_sql"], requires_confirmation_tools=["execute_sql"])

    Resolves toolset names from ``tools/toolsets.json`` (regenerate with
    ``uv run python parse_mcp_tools.py`` after editing any ``tools/*.yaml``).
    """
    tool_names: list[str] = []
    if toolset is not None:
        tool_names.extend(get_toolset(toolset) if isinstance(toolset, str) else get_toolsets(*toolset))
    if include_tools is not None:
        tool_names.extend(include_tools)

    auth_enabled = getenv("AUTH_ENABLED", "false").lower() in ("true", "1", "yes")
    auth_is_ibmi = False
    if auth_enabled:
        from auth.context import MCP_AUTH_MODE

        auth_is_ibmi = MCP_AUTH_MODE == "ibmi"

    mcp_kwargs: dict[str, Any] = {
        "url": url or MCP_URL,
        "transport": transport,
        "timeout_seconds": timeout_seconds,
        "refresh_connection": auth_is_ibmi,
    }
    if tool_names:
        mcp_kwargs["include_tools"] = tool_names

    if auth_is_ibmi and "header_provider" not in kwargs:
        from auth.mcp_tokens import mcp_header_provider

        mcp_kwargs["header_provider"] = mcp_header_provider

    mcp_kwargs |= kwargs

    if auth_is_ibmi:
        from agents.utils.lazy_mcp import LazyMCPTools

        return LazyMCPTools(**mcp_kwargs)
    return MCPTools(**mcp_kwargs)
