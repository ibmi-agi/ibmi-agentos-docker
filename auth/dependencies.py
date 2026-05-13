"""
Auth Dependencies
=================

FastAPI dependencies for scope-based authorization on specific routes.
"""

from __future__ import annotations

from fastapi import HTTPException, Request


def require_scope(scope: str):
    """FastAPI dependency that requires the authenticated key to have a specific scope.

    Usage::

        @router.post("/auth/keys")
        async def create_key(request: Request, _=Depends(require_scope("admin"))):
            ...
    """

    async def _check(request: Request) -> None:
        scopes: list[str] = getattr(request.state, "scopes", [])
        if "admin" in scopes:
            return  # Admin bypasses all scope checks
        if scope not in scopes:
            raise HTTPException(status_code=403, detail=f"Scope '{scope}' required")

    return _check


def require_auth(request: Request) -> None:
    """FastAPI dependency that requires the request to be authenticated.

    Always rejects unauthenticated requests, even when AUTH_ENABLED is false.
    This protects sensitive endpoints (like connection management) that should
    never be accessible without authentication.
    """
    if not getattr(request.state, "authenticated", False):
        raise HTTPException(status_code=401, detail="Authentication required")
