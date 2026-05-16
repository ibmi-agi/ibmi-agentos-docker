"""
Auth Router
===========

Key management endpoints: create, list, revoke, rotate.

All endpoints require ``admin`` scope except listing (which shows only metadata).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth.dependencies import require_auth, require_scope
from auth.service import AuthService

logger = logging.getLogger(__name__)

auth_router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class CreateKeyRequest(BaseModel):
    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Human-readable label for the key",
    )
    scopes: list[str] | None = Field(None, description="Permission scopes (defaults to agent/team/workflow run)")
    expires_at: datetime | None = Field(None, description="Optional expiration timestamp (UTC)")


class MeResponse(BaseModel):
    id: UUID
    name: str
    key_prefix: str
    scopes: list[str]
    is_active: bool
    created_at: datetime
    expires_at: datetime | None = None
    last_used_at: datetime | None = None


class KeyResponse(BaseModel):
    id: UUID
    name: str
    key_prefix: str
    scopes: list[str]
    is_active: bool
    created_at: datetime
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None
    connection_count: int = 0


class CreateKeyResponse(KeyResponse):
    key: str = Field(..., description="The API key — shown once, never stored. Save it now.")


# ---------------------------------------------------------------------------
# Singleton service (lazy init)
# ---------------------------------------------------------------------------

_service: AuthService | None = None


def _get_service() -> AuthService:
    global _service
    if _service is None:
        _service = AuthService()
    return _service


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@auth_router.get("/me", response_model=MeResponse)
async def get_me(
    request: Request,
    _: None = Depends(require_auth),
) -> dict[str, Any]:
    """Return metadata about the currently authenticated API key."""
    auth_key = getattr(request.state, "auth_key", None)
    if not auth_key:
        raise HTTPException(status_code=401, detail="Authentication required")
    return auth_key


@auth_router.post("/keys", response_model=CreateKeyResponse, status_code=201)
async def create_key(
    body: CreateKeyRequest,
    request: Request,
    _: None = Depends(require_scope("admin")),
) -> dict[str, Any]:
    """Create a new API key.

    The plaintext key is returned **once** in the response.
    Store it securely — it cannot be retrieved again.
    """
    svc = _get_service()
    result = svc.create_key(
        name=body.name,
        scopes=body.scopes,
        expires_at=body.expires_at,
    )
    return result


@auth_router.get("/keys", response_model=list[KeyResponse])
async def list_keys(
    request: Request,
    _: None = Depends(require_scope("admin")),
) -> list[dict[str, Any]]:
    """List all API keys (metadata only — no secrets)."""
    svc = _get_service()
    return svc.list_keys()


@auth_router.get("/keys/{key_id}", response_model=KeyResponse)
async def get_key(
    key_id: UUID,
    request: Request,
    _: None = Depends(require_scope("admin")),
) -> dict[str, Any]:
    """Get a single API key's metadata."""
    svc = _get_service()
    result = svc.get_key(key_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Key not found")
    return result


@auth_router.delete("/keys/{key_id}", status_code=204)
async def revoke_key(
    key_id: UUID,
    request: Request,
    _: None = Depends(require_scope("admin")),
) -> None:
    """Revoke an API key immediately."""
    svc = _get_service()
    if not svc.revoke_key(key_id):
        raise HTTPException(status_code=404, detail="Key not found or already revoked")


@auth_router.post("/keys/{key_id}/rotate", response_model=CreateKeyResponse, status_code=201)
async def rotate_key(
    key_id: UUID,
    request: Request,
    _: None = Depends(require_scope("admin")),
) -> dict[str, Any]:
    """Rotate an API key: revoke the old one and create a new one with the same name and scopes.

    The new plaintext key is returned **once**.
    """
    svc = _get_service()
    result = svc.rotate_key(key_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Key not found")
    return result
