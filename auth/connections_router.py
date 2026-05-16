"""
Connections Router
==================

REST API for managing IBM i system connections.

All endpoints require authentication and are scoped to the caller's API key.
Credentials are encrypted at rest and never returned in API responses.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth.connections import ConnectionsService
from auth.dependencies import require_auth, require_scope
from auth.mcp_tokens import MCPAuthError, get_token_manager

if TYPE_CHECKING:
    from auth.mcp_tokens import MCPTokenManager

logger = logging.getLogger(__name__)

connections_router = APIRouter(
    prefix="/auth/connections",
    tags=["connections"],
    dependencies=[Depends(require_auth)],
)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class CreateConnectionRequest(BaseModel):
    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Human-readable label (e.g., 'Production LPAR')",
    )
    host: str = Field(..., min_length=1, max_length=255, description="IBM i hostname or IP")
    port: int = Field(8076, ge=1, le=65535, description="Mapepire port")
    user: str = Field(..., min_length=1, max_length=128, description="IBM i user profile")
    password: str = Field(..., min_length=1, max_length=512, description="IBM i password")
    is_default: bool = Field(False, description="Set as the default connection for this API key")


class UpdateConnectionRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    host: str | None = Field(None, min_length=1, max_length=255)
    port: int | None = Field(None, ge=1, le=65535)
    user: str | None = Field(None, min_length=1, max_length=128)
    password: str | None = Field(None, min_length=1, max_length=512)


class ConnectionResponse(BaseModel):
    id: UUID
    api_key_id: UUID
    name: str
    host: str
    port: int
    ibmi_user: str
    is_default: bool
    is_active: bool
    created_at: Any
    updated_at: Any | None = None
    last_connected: Any | None = None


class TestConnectionResponse(BaseModel):
    success: bool
    message: str


# ---------------------------------------------------------------------------
# Shared service singletons
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _get_conn_service() -> ConnectionsService:
    return ConnectionsService()


def _get_token_manager() -> "MCPTokenManager":
    return get_token_manager()


def _get_api_key_id(request: Request) -> UUID:
    """Extract the authenticated API key ID from request state."""
    auth_key = getattr(request.state, "auth_key", None)
    if auth_key and "id" in auth_key:
        return UUID(str(auth_key["id"]))
    user_id = getattr(request.state, "user_id", None)
    if user_id and user_id != "__legacy__":
        return UUID(str(user_id))
    raise HTTPException(status_code=401, detail="Cannot determine API key identity")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


class AdminConnectionResponse(ConnectionResponse):
    api_key_name: str | None = None


@connections_router.get(
    "/admin/all",
    response_model=list[AdminConnectionResponse],
    dependencies=[Depends(require_scope("admin"))],
)
async def list_all_connections(api_key_id: UUID | None = None) -> list[dict[str, Any]]:
    """List all connections across all API keys (admin only)."""
    return _get_conn_service().list_all_connections(api_key_id)


@connections_router.post("", response_model=ConnectionResponse, status_code=201)
async def create_connection(
    body: CreateConnectionRequest,
    request: Request,
) -> dict[str, Any]:
    """Register a new IBM i system connection."""
    api_key_id = _get_api_key_id(request)
    svc = _get_conn_service()

    try:
        result = svc.create_connection(
            api_key_id=api_key_id,
            name=body.name,
            host=body.host,
            ibmi_user=body.user,
            ibmi_password=body.password,
            port=body.port,
            is_default=body.is_default,
        )
    except Exception as exc:
        if "unique" in str(exc).lower():
            raise HTTPException(
                status_code=409,
                detail=f"Connection named '{body.name}' already exists",
            ) from exc
        raise

    return result


@connections_router.get("", response_model=list[ConnectionResponse])
async def list_connections(request: Request) -> list[dict[str, Any]]:
    """List all connections for the authenticated API key."""
    api_key_id = _get_api_key_id(request)
    return _get_conn_service().list_connections(api_key_id)


@connections_router.get("/{connection_id}", response_model=ConnectionResponse)
async def get_connection(connection_id: UUID, request: Request) -> dict[str, Any]:
    """Get a single connection by ID."""
    api_key_id = _get_api_key_id(request)
    result = _get_conn_service().get_connection(connection_id, api_key_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Connection not found")
    return result


@connections_router.put("/{connection_id}", response_model=ConnectionResponse)
async def update_connection(
    connection_id: UUID,
    body: UpdateConnectionRequest,
    request: Request,
) -> dict[str, Any]:
    """Update a connection's settings or credentials."""
    api_key_id = _get_api_key_id(request)
    svc = _get_conn_service()

    result = svc.update_connection(
        connection_id,
        api_key_id,
        name=body.name,
        host=body.host,
        port=body.port,
        ibmi_user=body.user,
        ibmi_password=body.password,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Connection not found")

    _get_token_manager().invalidate(connection_id)
    return result


@connections_router.delete("/{connection_id}", status_code=204)
async def delete_connection(connection_id: UUID, request: Request) -> None:
    """Delete a connection and invalidate its cached token."""
    api_key_id = _get_api_key_id(request)
    if not _get_conn_service().delete_connection(connection_id, api_key_id):
        raise HTTPException(status_code=404, detail="Connection not found")
    _get_token_manager().invalidate(connection_id)


@connections_router.put("/{connection_id}/default", response_model=ConnectionResponse)
async def set_default_connection(connection_id: UUID, request: Request) -> dict[str, Any]:
    """Set a connection as the default for the authenticated API key."""
    api_key_id = _get_api_key_id(request)
    svc = _get_conn_service()

    if not svc.set_default(connection_id, api_key_id):
        raise HTTPException(status_code=404, detail="Connection not found")

    result = svc.get_connection(connection_id, api_key_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Connection not found")
    return result


@connections_router.post("/{connection_id}/test", response_model=TestConnectionResponse)
async def test_connection(connection_id: UUID, request: Request) -> dict[str, Any]:
    """Test a connection by attempting MCP server authentication."""
    api_key_id = _get_api_key_id(request)
    svc = _get_conn_service()
    tm = _get_token_manager()

    creds = svc.get_connection_credentials(connection_id, api_key_id)
    if creds is None:
        raise HTTPException(status_code=404, detail="Connection not found")

    try:
        await tm.get_token(
            connection_id=connection_id,
            host=creds["host"],
            port=creds["port"],
            user=creds["user"],
            password=creds["password"],
        )
        svc.touch_last_connected(connection_id)
        return {"success": True, "message": "Connection successful"}
    except MCPAuthError as exc:
        tm.invalidate(connection_id)
        logger.warning("Connection test auth failed for %s: %s", connection_id, exc)
        return {
            "success": False,
            "message": "MCP server authentication failed. Check credentials and server configuration.",
        }
    except Exception as exc:
        tm.invalidate(connection_id)
        logger.exception("Connection test failed for %s: %s", connection_id, exc)
        return {
            "success": False,
            "message": "Connection failed. Check host, port, and server availability.",
        }
