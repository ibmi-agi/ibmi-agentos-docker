"""Lazy-connecting MCPTools for per-request authentication.

At startup (no auth token available), registers tool name stubs so Agno
knows the tools exist.  On the first agent run — when the auth middleware
has set the context-variable token — the real MCP connection is made and
stubs are replaced with fully-typed implementations from the server.
"""

from __future__ import annotations

import logging
import warnings
from typing import Any

from agno.tools.function import Function
from agno.tools.mcp import MCPTools, SSEClientParams, StreamableHTTPClientParams

logger = logging.getLogger(__name__)


class LazyMCPTools(MCPTools):
    """MCPTools that defers connection until auth credentials are available.

    Lifecycle:
    1. ``connect()`` at startup — no token → register name-only stubs
    2. ``connect()`` during agent run — token available → real MCP connect,
       stubs replaced with server-provided tools (correct schemas)
    3. LLM sees real tool schemas and calls tools normally
    """

    _real_connected: bool = False
    server_params: Any

    # ------------------------------------------------------------------
    # connect() — called by Agno at startup AND before each agent run
    # ------------------------------------------------------------------

    async def connect(self, force: bool = False) -> None:  # type: ignore[override]
        if force:
            self._real_connected = False
            self._initialized = False
            self.session = None
            self._context = None
            self._session_context = None

        # Already fully connected — nothing to do
        if self._real_connected:
            return

        # Try to get auth headers from header_provider (reads contextvar)
        headers = self._get_auth_headers()

        if headers:
            # Auth token available (during agent run) — do real connect
            self._inject_headers(headers)
            self._initialized = False
            self.session = None
            await super()._connect()
            self._real_connected = True
            logger.info(
                "LazyMCPTools: connected with auth, %d tools registered",
                len(self.functions),
            )
        elif not self._initialized and self.include_tools:
            # No auth yet (startup) — register stubs so Agno sees the tool names
            self._register_stubs()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_auth_headers(self) -> dict | None:
        """Read auth headers from header_provider, return None if unavailable."""
        if not self.header_provider:
            return None
        headers = self._call_header_provider()
        return headers if headers else None

    def _inject_headers(self, headers: dict) -> None:
        """Set auth headers on server_params for the transport layer."""
        if self.transport not in ("streamable-http", "sse"):
            return
        ParamsCls = (
            StreamableHTTPClientParams
            if self.transport == "streamable-http"
            else SSEClientParams
        )
        if self.server_params is None:
            self.server_params = ParamsCls(url=self.url or "", headers=headers)
        else:
            existing = getattr(self.server_params, "headers", None) or {}
            self.server_params.headers = {**existing, **headers}  # type: ignore[union-attr]

    def _register_stubs(self) -> None:
        """Register name-only stubs so Agno knows the tools exist at startup."""
        for name in self.include_tools or []:
            self.functions[name] = Function(
                name=name,
                description=f"IBM i tool: {name} (connecting...)",
                parameters={"type": "object", "properties": {}},
                entrypoint=self._make_stub(name),
                skip_entrypoint_processing=True,
            )
        self._initialized = True
        logger.debug("LazyMCPTools: registered %d tool stubs", len(self.functions))

    def _make_stub(self, tool_name: str):
        """Stub entrypoint that triggers real connection, then retries."""

        async def _stub(**kwargs):  # noqa: ARG001
            # This should rarely execute — connect() should upgrade stubs
            # before the LLM calls tools.  But as a safety net:
            if not self._real_connected:
                headers = self._get_auth_headers()
                if headers:
                    self._inject_headers(headers)
                    self._initialized = False
                    self.session = None
                    await MCPTools._connect(self)
                    self._real_connected = True
                    # Retry with real entrypoint
                    fn = self.functions.get(tool_name)
                    if fn and fn.entrypoint is not None:
                        return await fn.entrypoint(**kwargs)
                raise RuntimeError(
                    f"Tool {tool_name} unavailable — no MCP auth token in context"
                )
            fn = self.functions.get(tool_name)
            if fn and fn.entrypoint is not None:
                return await fn.entrypoint(**kwargs)
            raise RuntimeError(f"Tool {tool_name} not found after MCP connect")

        return _stub

    # ------------------------------------------------------------------
    # Graceful cleanup (cancel-scope safe)
    # ------------------------------------------------------------------

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore", category=RuntimeWarning, message=".*async_generator.*"
            )
            try:
                await super().__aexit__(exc_type, exc_val, exc_tb)
            except RuntimeError as e:
                if "cancel scope" not in str(e).lower():
                    raise
            except Exception:
                logger.debug("LazyMCPTools: cleanup error (non-fatal)", exc_info=True)
            finally:
                self._initialized = False
                self._real_connected = False
                self.session = None

    async def close(self) -> None:  # type: ignore[override]
        if not self._initialized and not self._real_connected:
            return
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore", category=RuntimeWarning, message=".*async_generator.*"
            )
            try:
                await super().close()
            except RuntimeError as e:
                if "cancel scope" not in str(e).lower():
                    raise
            except Exception:
                logger.debug("LazyMCPTools: close error (non-fatal)", exc_info=True)
            finally:
                self._initialized = False
                self._real_connected = False
                self.session = None
