"""
Auth Module
===========

API key authentication and multi-user IBM i connection management for AgentOS.
"""

from auth.middleware import APIKeyAuthMiddleware
from auth.router import auth_router
from auth.service import AuthService

__all__ = [
    "APIKeyAuthMiddleware",
    "AuthService",
    "auth_router",
]
