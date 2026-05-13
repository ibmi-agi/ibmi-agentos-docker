"""
MCP Token Manager
=================

Handles the RSA-encrypted credential exchange with the IBM i MCP server
(``MCP_AUTH_MODE=ibmi``) and caches Bearer tokens per connection.

Also provides ``mcp_header_provider`` — a sync callback for Agno's
``MCPTools(header_provider=...)`` that reads the per-request token
from a context variable set by the auth middleware.

Flow:
1. Fetch the MCP server's RSA public key (``GET /api/v1/auth/public-key``)
2. Encrypt IBM i credentials with AES-256-GCM, wrap the AES key with RSA
3. Send encrypted payload to ``POST /api/v1/auth``
4. Cache the returned Bearer token until near-expiry
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any
from uuid import UUID

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from agents.config import MCP_UPSTREAM_URL
from auth.context import mcp_auth_token

logger = logging.getLogger(__name__)

# Proactive refresh: renew tokens at 80% of their lifetime
_REFRESH_FACTOR = 0.8

# Default token expiry (matches MCP server default)
_DEFAULT_EXPIRY_SECONDS = 3600

# Maximum number of cached tokens (prevents unbounded memory growth)
_MAX_CACHE_SIZE = 500


def mcp_header_provider(**kwargs: Any) -> dict[str, Any]:  # noqa: ARG001
    """Agno MCPTools header_provider callback.

    Reads the per-request MCP Bearer token from the context variable
    set by the auth middleware. Returns empty dict if no token is set
    (e.g., when MCP_AUTH_MODE is not 'ibmi' or no connection configured).
    """
    token = mcp_auth_token.get()
    if token:
        logger.debug("header_provider: injecting Bearer token (%s...)", token[:20])
        return {"Authorization": f"Bearer {token}"}
    logger.warning(
        "header_provider: no MCP auth token in context — request will be unauthenticated"
    )
    return {}


@dataclass
class MCPTokenEntry:
    """Cached MCP Bearer token for a specific connection."""

    token: str
    created_at: float
    expires_at: float
    connection_id: UUID


@dataclass
class MCPTokenManager:
    """Manages MCP Bearer tokens for IBM i connections.

    One manager instance per application — tokens are cached in memory
    keyed by connection ID.
    """

    mcp_base_url: str = ""
    token_expiry_seconds: int = _DEFAULT_EXPIRY_SECONDS
    _cache: dict[UUID, MCPTokenEntry] = field(default_factory=dict)
    _public_key_pem: bytes | None = field(default=None, repr=False)
    _public_key_fetched_at: float = 0.0
    _client: httpx.AsyncClient | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not self.mcp_base_url:
            self.mcp_base_url = MCP_UPSTREAM_URL
        self.mcp_base_url = self.mcp_base_url.rstrip("/")
        if self.mcp_base_url.endswith("/mcp"):
            self.mcp_base_url = self.mcp_base_url[:-4]

    async def _get_client(self) -> httpx.AsyncClient:
        """Return a shared httpx client, creating it on first use."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_token(
        self,
        connection_id: UUID,
        host: str,
        port: str,
        user: str,
        password: str,
    ) -> str:
        """Get a valid MCP Bearer token for a connection, fetching or refreshing as needed."""
        cached = self._cache.get(connection_id)
        if cached and not self._is_near_expiry(cached):
            return cached.token

        token = await self._acquire_token(self.mcp_base_url, host, port, user, password)
        now = time.time()

        # Evict expired entries before adding new ones to bound memory
        if len(self._cache) >= _MAX_CACHE_SIZE:
            self._evict_expired()

        self._cache[connection_id] = MCPTokenEntry(
            token=token,
            created_at=now,
            expires_at=now + self.token_expiry_seconds,
            connection_id=connection_id,
        )
        logger.info("MCP token acquired for connection %s", connection_id)
        return token

    def invalidate(self, connection_id: UUID) -> None:
        """Remove a cached token (e.g., on credential change or 401)."""
        self._cache.pop(connection_id, None)

    def invalidate_all(self) -> None:
        """Clear all cached tokens."""
        self._cache.clear()
        self._public_key_pem = None

    # ------------------------------------------------------------------
    # RSA encryption flow
    # ------------------------------------------------------------------

    async def _acquire_token(
        self,
        base_url: str,
        host: str,
        port: str,
        user: str,
        password: str,
    ) -> str:
        """Execute the full RSA-encrypted auth flow with the MCP server."""
        public_key_pem = await self._fetch_public_key(base_url)
        encrypted_payload = self._encrypt_credentials(
            public_key_pem, host, port, user, password
        )

        client = await self._get_client()
        resp = await client.post(f"{base_url}/api/v1/auth", json=encrypted_payload)
        if resp.status_code not in (200, 201):
            body = resp.text
            logger.error("MCP auth failed: status=%d body=%s", resp.status_code, body)
            raise MCPAuthError(
                f"MCP server auth failed with status {resp.status_code}: {body}"
            )

        data = resp.json()
        token = data.get("token") or data.get("access_token")
        if not token:
            raise MCPAuthError(
                f"MCP auth response missing token field: {list(data.keys())}"
            )
        return token

    async def _fetch_public_key(self, base_url: str) -> bytes:
        """Fetch and cache the MCP server's RSA public key (5-minute TTL)."""
        if self._public_key_pem and (time.time() - self._public_key_fetched_at) < 300:
            return self._public_key_pem

        client = await self._get_client()
        resp = await client.get(f"{base_url}/api/v1/auth/public-key")
        if resp.status_code != 200:
            raise MCPAuthError(
                f"Failed to fetch MCP public key: status {resp.status_code}"
            )

        data = resp.json()
        pem = data.get("publicKey") or data.get("public_key") or data.get("key")
        if not pem:
            raise MCPAuthError(
                f"MCP public key response missing key field: {list(data.keys())}"
            )

        key_pem: bytes = pem.encode() if isinstance(pem, str) else pem
        self._public_key_pem = key_pem
        self._public_key_fetched_at = time.time()
        return key_pem

    @staticmethod
    def _encrypt_credentials(
        public_key_pem: bytes,
        host: str,
        port: str,
        user: str,
        password: str,
    ) -> dict[str, str]:
        """Encrypt credentials using RSA + AES-256-GCM (hybrid encryption).

        Matches the encryption scheme expected by the IBM i MCP server:
        1. Generate a random 256-bit AES key
        2. Encrypt the credentials JSON with AES-256-GCM
        3. Wrap the AES key with the server's RSA public key (OAEP + SHA-256)
        4. Return the encrypted payload as base64-encoded fields
        """
        public_key = serialization.load_pem_public_key(public_key_pem)

        cred_json = json.dumps(
            {
                "credentials": {
                    "username": user,
                    "password": password,
                },
                "request": {
                    "host": host,
                    "port": int(port),
                },
            }
        ).encode()

        aes_key = AESGCM.generate_key(bit_length=256)
        nonce = os.urandom(12)

        aesgcm = AESGCM(aes_key)
        ciphertext_with_tag = aesgcm.encrypt(nonce, cred_json, None)

        # AES-GCM appends a 16-byte auth tag; MCP server expects them separate
        ciphertext = ciphertext_with_tag[:-16]
        auth_tag = ciphertext_with_tag[-16:]

        encrypted_key = public_key.encrypt(  # type: ignore[union-attr]
            aes_key,
            asym_padding.OAEP(
                mgf=asym_padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )

        key_id = os.getenv("IBMI_AUTH_KEY_ID", "ibmi-agentos")

        return {
            "keyId": key_id,
            "encryptedSessionKey": base64.b64encode(encrypted_key).decode(),
            "iv": base64.b64encode(nonce).decode(),
            "authTag": base64.b64encode(auth_tag).decode(),
            "ciphertext": base64.b64encode(ciphertext).decode(),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_near_expiry(self, entry: MCPTokenEntry) -> bool:
        """Check if a token is near expiry (past 80% of its lifetime)."""
        lifetime = entry.expires_at - entry.created_at
        threshold = entry.created_at + (lifetime * _REFRESH_FACTOR)
        return time.time() >= threshold

    def _evict_expired(self) -> None:
        """Remove expired entries from the cache to bound memory growth."""
        now = time.time()
        expired = [cid for cid, entry in self._cache.items() if entry.expires_at <= now]
        for cid in expired:
            del self._cache[cid]
        if expired:
            logger.debug("Evicted %d expired MCP token cache entries", len(expired))


class MCPAuthError(Exception):
    """Raised when MCP server authentication fails."""


@lru_cache(maxsize=1)
def get_token_manager() -> MCPTokenManager:
    """Return a process-wide singleton MCPTokenManager.

    All callers (middleware, router, etc.) MUST use this function
    to ensure token invalidation propagates everywhere.
    """
    return MCPTokenManager()
