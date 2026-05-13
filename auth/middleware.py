"""
API Key Auth Middleware
======================

Starlette middleware that validates API keys on every request.

Skips health/status endpoints. Falls back to OS_SECURITY_KEY if configured.
Sets ``request.state.auth_key`` with key metadata on success.

When multi-user auth is enabled (``MCP_AUTH_MODE=ibmi``), also resolves the
caller's IBM i system connection and sets the ``mcp_auth_token`` context
variable so the MCPTools header_provider can inject per-user Bearer tokens.
"""

from __future__ import annotations

import heapq
import logging
import time
from os import getenv
from typing import TYPE_CHECKING
from uuid import UUID

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

if TYPE_CHECKING:
    from starlette.types import ASGIApp

    from auth.connections import ConnectionsService
    from auth.mcp_tokens import MCPTokenManager

from auth.context import (
    MCP_AUTH_MODE,
    current_api_key_id,
    mcp_auth_token,
    mcp_connection_id,
)
from auth.rate_limit import RateLimiter
from auth.service import AuthService

logger = logging.getLogger(__name__)

# Paths that never require authentication
EXEMPT_PATHS = frozenset(
    {
        "/health",
        "/healthz",
        "/status",
        "/openapi.json",
        "/docs",
        "/redoc",
        "/favicon.ico",
    }
)

# Path prefixes that never require authentication
EXEMPT_PREFIXES = (
    "/docs",
    "/redoc",
)

# Throttle touch_last_connected to at most once per 5 minutes per connection
_TOUCH_INTERVAL_SECONDS = 300
# Bound _last_touch dict to prevent unbounded memory growth
_MAX_TOUCH_ENTRIES = 1000


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """Validate ``Authorization: Bearer <key>`` on every request.

    Auth is skipped when ``AUTH_ENABLED`` is not ``true``.

    Verification order:
    1. Check API keys table (hashed lookup)
    2. Fall back to ``OS_SECURITY_KEY`` env var (legacy single-token)
    3. Reject with 401

    When ``MCP_AUTH_MODE=ibmi``, after successful API key auth the middleware
    resolves the user's IBM i system connection and acquires an MCP Bearer
    token, setting context variables for the MCPTools header_provider.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._enabled = getenv("AUTH_ENABLED", "").lower() == "true"
        self._auth_service: AuthService | None = None
        self._rate_limiter: RateLimiter | None = None
        self._os_security_key = getenv("OS_SECURITY_KEY", "")
        self._initialized = False
        # Lazy-loaded connection services (only when MCP_AUTH_MODE=ibmi)
        self._conn_service: ConnectionsService | None = None
        self._token_manager: MCPTokenManager | None = None
        # Track last touch time per connection to throttle DB writes
        self._last_touch: dict[UUID, float] = {}

    def _lazy_init(self) -> None:
        """Initialize DB-dependent objects on first request (not import time)."""
        if self._initialized:
            return
        try:
            self._auth_service = AuthService()
            self._rate_limiter = RateLimiter()
            master_key = getenv("AUTH_MASTER_KEY", "")
            if master_key and self._auth_service:
                self._auth_service.bootstrap_from_env(master_key)

            if MCP_AUTH_MODE == "ibmi":
                # Validate required config before initializing
                if not getenv("AUTH_ENCRYPTION_KEY", ""):
                    logger.error(
                        "MCP_AUTH_MODE=ibmi requires AUTH_ENCRYPTION_KEY. "
                        "Generate one with: python -c "
                        '"from cryptography.fernet import Fernet; '
                        'print(Fernet.generate_key().decode())"'
                    )
                    raise RuntimeError(
                        "AUTH_ENCRYPTION_KEY is required when MCP_AUTH_MODE=ibmi"
                    )

                from auth.connections import ConnectionsService
                from auth.mcp_tokens import get_token_manager

                self._conn_service = ConnectionsService()
                self._token_manager = get_token_manager()
                logger.info("Multi-user MCP auth enabled (MCP_AUTH_MODE=ibmi)")

            self._initialized = True
        except Exception:
            logger.exception(
                "Failed to initialize auth service — will retry on next request"
            )

    async def _resolve_mcp_connection(self, request: Request) -> None:
        """Resolve the user's IBM i connection and acquire an MCP token.

        Sets context variables for the MCPTools header_provider.
        Also sets ``request.state.mcp_auth_status`` so downstream handlers
        and response middleware can surface connection state to clients.

        Status values: "ok", "no-connection", "credential-error", "auth-failed"
        """
        if not self._conn_service or not self._token_manager:
            return

        auth_key = getattr(request.state, "auth_key", None)
        if not auth_key or "id" not in auth_key:
            return

        api_key_id = UUID(str(auth_key["id"]))
        conn_svc = self._conn_service

        # Check for explicit connection selection via header
        conn_header_raw = request.headers.get("x-system-connection")

        conn = None
        if conn_header_raw is not None:
            conn_header = conn_header_raw.strip()
            if not conn_header:
                request.state.mcp_auth_status = "invalid-connection"
                logger.warning("X-System-Connection header is empty")
                return

            try:
                conn_id = UUID(conn_header)
                conn = conn_svc.get_connection(conn_id, api_key_id)
            except ValueError:
                conn = conn_svc.get_connection_by_name(conn_header, api_key_id)

            if conn is None:
                request.state.mcp_auth_status = "invalid-connection"
                logger.warning(
                    "X-System-Connection header value not found: %s", conn_header
                )
                return
        else:
            conn = conn_svc.get_default_connection(api_key_id)

        if conn is None:
            request.state.mcp_auth_status = "no-connection"
            return

        connection_id = UUID(str(conn["id"]))
        creds = conn_svc.get_connection_credentials(connection_id, api_key_id)
        if creds is None:
            logger.warning(
                "Could not decrypt credentials for connection %s", connection_id
            )
            request.state.mcp_auth_status = "credential-error"
            return

        try:
            token = await self._token_manager.get_token(
                connection_id=connection_id,
                host=creds["host"],
                port=creds["port"],
                user=creds["user"],
                password=creds["password"],
            )
            mcp_auth_token.set(token)
            mcp_connection_id.set(connection_id)

            request.state.mcp_token = token
            request.state.mcp_connection_id = str(connection_id)
            request.state.mcp_auth_status = "ok"
            logger.debug(
                "MCP connection resolved: connection=%s host=%s user=%s token=%s...",
                connection_id,
                creds["host"],
                creds["user"],
                token[:20],
            )

            # Throttled touch — only write if >5 minutes since last
            now = time.time()
            last = self._last_touch.get(connection_id, 0.0)
            if now - last > _TOUCH_INTERVAL_SECONDS:
                conn_svc.touch_last_connected(connection_id)
                self._last_touch[connection_id] = now
                # Prune oldest entries if dict grows too large
                if len(self._last_touch) > _MAX_TOUCH_ENTRIES:
                    oldest = heapq.nsmallest(
                        100, self._last_touch.items(), key=lambda kv: kv[1]
                    )
                    for k, _ in oldest:
                        del self._last_touch[k]

        except Exception:
            logger.exception(
                "Failed to acquire MCP token for connection %s", connection_id
            )
            request.state.mcp_auth_status = "auth-failed"

    def _check_rate_limit(self, bucket: str, log_fields: str) -> JSONResponse | None:
        """Return a 429 JSONResponse if *bucket* is rate-limited, else None.

        ``log_fields`` is appended to the warning log to identify the caller
        (e.g., ``"ip=1.2.3.4 path=/foo"`` or ``"key_prefix=ixr_abc path=/foo"``).
        """
        if not self._rate_limiter:
            return None
        allowed, headers = self._rate_limiter.check(bucket)
        if allowed:
            return None
        logger.warning("Rate limit exceeded: %s", log_fields)
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
            headers=headers,
        )

    def _authenticate(self, token: str) -> dict | None:
        """Verify *token* against the API keys table.

        Returns the matched key metadata, or None if no match.
        """
        if self._auth_service is None:
            return None
        return self._auth_service.verify_key(token)

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        if not self._enabled:
            return await call_next(request)

        path = request.url.path.rstrip("/")
        if path in EXEMPT_PATHS or path.startswith(EXEMPT_PREFIXES):
            return await call_next(request)

        if request.method == "OPTIONS":
            return await call_next(request)

        self._lazy_init()

        if self._auth_service is None:
            return JSONResponse(
                status_code=503,
                content={"detail": "Auth service unavailable — try again shortly"},
            )

        auth_header = request.headers.get("authorization", "")
        if not auth_header.lower().startswith("bearer "):
            return self._unauthorized("Authorization header required (Bearer token)")

        token = auth_header[7:]
        if not token:
            return self._unauthorized("Empty bearer token")

        client_ip = request.client.host if request.client else "unknown"
        ip_limited = self._check_rate_limit(client_ip, f"ip={client_ip} path={path}")
        if ip_limited is not None:
            return ip_limited

        # 1. Try API keys table
        key_meta = self._authenticate(token)
        if key_meta:
            key_prefix = key_meta.get("key_prefix", "?")
            key_limited = self._check_rate_limit(
                f"key:{key_meta['id']}", f"key_prefix={key_prefix} path={path}"
            )
            if key_limited is not None:
                return key_limited

            request.state.authenticated = True
            request.state.auth_key = key_meta
            request.state.user_id = str(key_meta["id"])
            request.state.scopes = key_meta.get("scopes", [])
            current_api_key_id.set(UUID(str(key_meta["id"])))

            if MCP_AUTH_MODE == "ibmi":
                await self._resolve_mcp_connection(request)
                if (
                    getattr(request.state, "mcp_auth_status", None)
                    == "invalid-connection"
                ):
                    conn_val = request.headers.get("x-system-connection", "")
                    return JSONResponse(
                        status_code=400,
                        content={
                            "detail": f"Connection not found: {conn_val}",
                            "x_mcp_auth_status": "invalid-connection",
                        },
                    )

            logger.info(
                "auth_success key_prefix=%s key_name=%s method=%s path=%s",
                key_prefix,
                key_meta.get("name", "?"),
                request.method,
                path,
            )
            response = await call_next(request)
            mcp_status = getattr(request.state, "mcp_auth_status", None)
            if mcp_status:
                response.headers["X-MCP-Auth-Status"] = mcp_status
            return response

        # 2. Fall back to OS_SECURITY_KEY
        if self._os_security_key and AuthService.verify_legacy_key(
            token, self._os_security_key
        ):
            request.state.authenticated = True
            request.state.user_id = "__legacy__"
            request.state.scopes = ["admin", "agents:run", "teams:run", "workflows:run"]

            logger.info("auth_success_legacy method=%s path=%s", request.method, path)
            return await call_next(request)

        # 3. Reject
        logger.warning(
            "auth_failure reason=invalid_key method=%s path=%s ip=%s",
            request.method,
            path,
            client_ip,
        )
        return self._unauthorized("Invalid API key")

    @staticmethod
    def _unauthorized(detail: str) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content={"detail": detail},
            headers={"WWW-Authenticate": "Bearer"},
        )
