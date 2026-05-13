"""CLI child-process environment scrubbing.

MCP-server-only env vars leak into the ``ibmi`` CLI from the shared
``.env`` and crash startup when the CLI tries to read key paths that
only exist for the MCP server. Stripping them forces the CLI to fall
back to ``~/.ibmi/config.yaml``.
"""

from __future__ import annotations

import os

_IBMI_MCP_SERVER_ENV_VARS = frozenset(
    {
        "IBMI_HTTP_AUTH_ENABLED",
        "IBMI_AUTH_PRIVATE_KEY_PATH",
        "IBMI_AUTH_PUBLIC_KEY_PATH",
        "IBMI_AUTH_KEY_ID",
        "IBMI_AUTH_ALLOW_HTTP",
        "IBMI_AUTH_TOKEN_EXPIRY_SECONDS",
        "IBMI_AUTH_MAX_CONCURRENT_SESSIONS",
        "MCP_AUTH_MODE",
    }
)


def _scrub_child_env() -> dict[str, str]:
    """Copy of ``os.environ`` with MCP-server-only vars removed."""
    return {k: v for k, v in os.environ.items() if k not in _IBMI_MCP_SERVER_ENV_VARS}
