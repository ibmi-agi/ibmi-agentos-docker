"""
Auth Service
============

API key generation, hashing, and CRUD operations.

Keys follow the format: ``ixr_<base64url-encoded random bytes>``
Only the SHA-256 hash is persisted — the plaintext is returned exactly once at creation time.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Engine

from db.engine import get_engine

logger = logging.getLogger(__name__)

KEY_PREFIX = "ixr_"
KEY_BYTE_LENGTH = 32  # 256-bit entropy

# Default scopes for new keys
DEFAULT_SCOPES = ["agents:run", "teams:run", "workflows:run"]

# ---------------------------------------------------------------------------
# Table DDL — idempotent, runs on first use
# ---------------------------------------------------------------------------

_CREATE_TABLE_SQL = text("""
CREATE TABLE IF NOT EXISTS api_keys (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name          VARCHAR(255) NOT NULL,
    key_hash      VARCHAR(64) NOT NULL UNIQUE,
    key_prefix    VARCHAR(16) NOT NULL,
    scopes        JSONB NOT NULL DEFAULT '["agents:run", "teams:run", "workflows:run"]'::jsonb,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at    TIMESTAMPTZ,
    revoked_at    TIMESTAMPTZ,
    last_used_at  TIMESTAMPTZ
)
""")

_CREATE_INDEX_SQL = text("""
CREATE INDEX IF NOT EXISTS idx_api_keys_key_hash ON api_keys (key_hash)
""")


class AuthService:
    """Manages API key lifecycle — create, verify, revoke, rotate, list."""

    def __init__(self, engine: Engine | None = None) -> None:
        self.engine = engine or get_engine()
        self._ensure_table()

    def _ensure_table(self) -> None:
        """Create the api_keys table if it doesn't exist.

        Also ensures system_connections exists since list_keys() joins it.
        """
        from auth.connections import ConnectionsService

        with self.engine.begin() as conn:
            conn.execute(_CREATE_TABLE_SQL)
            conn.execute(_CREATE_INDEX_SQL)
        ConnectionsService(engine=self.engine)

    # ------------------------------------------------------------------
    # Key generation
    # ------------------------------------------------------------------

    @staticmethod
    def generate_key() -> str:
        """Generate a new API key with the ``ixr_`` prefix."""
        raw = secrets.token_urlsafe(KEY_BYTE_LENGTH)
        return f"{KEY_PREFIX}{raw}"

    @staticmethod
    def hash_key(key: str) -> str:
        """SHA-256 hash of the full key string."""
        return hashlib.sha256(key.encode()).hexdigest()

    @staticmethod
    def get_prefix(key: str) -> str:
        """Extract a safe display prefix from the key (first 12 chars)."""
        return key[:12]

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create_key(
        self,
        name: str,
        scopes: list[str] | None = None,
        expires_at: datetime | None = None,
    ) -> dict[str, Any]:
        """Create a new API key. Returns dict with plaintext ``key`` (shown once)."""
        import json

        plaintext = self.generate_key()
        key_hash = self.hash_key(plaintext)
        key_prefix = self.get_prefix(plaintext)
        key_scopes = scopes or DEFAULT_SCOPES

        with self.engine.begin() as conn:
            result = conn.execute(
                text("""
                    INSERT INTO api_keys (name, key_hash, key_prefix, scopes, expires_at)
                    VALUES (:name, :key_hash, :key_prefix, CAST(:scopes AS jsonb), :expires_at)
                    RETURNING id, name, key_prefix, scopes, is_active, created_at, expires_at
                """),
                {
                    "name": name,
                    "key_hash": key_hash,
                    "key_prefix": key_prefix,
                    "scopes": json.dumps(key_scopes),
                    "expires_at": expires_at,
                },
            )
            row = result.mappings().fetchone()

        record = dict(row) if row else {}
        record["key"] = plaintext  # Returned once, never stored
        logger.info("API key created: name=%s prefix=%s", name, key_prefix)
        return record

    def verify_key(self, key: str) -> dict[str, Any] | None:
        """Verify an API key. Returns key metadata if valid, None otherwise.

        A key is valid if:
        - Its hash matches a row in the table
        - ``is_active`` is True
        - ``revoked_at`` is NULL
        - ``expires_at`` is NULL or in the future
        """
        key_hash = self.hash_key(key)
        now = datetime.now(timezone.utc)

        with self.engine.begin() as conn:
            result = conn.execute(
                text("""
                    SELECT id, name, key_prefix, scopes, is_active,
                           created_at, expires_at, revoked_at, last_used_at
                    FROM api_keys
                    WHERE key_hash = :key_hash
                """),
                {"key_hash": key_hash},
            )
            row = result.mappings().fetchone()

        if row is None:
            return None

        record = dict(row)

        # Check active
        if not record["is_active"]:
            return None

        # Check revoked
        if record["revoked_at"] is not None:
            return None

        # Check expired
        if record["expires_at"] is not None and record["expires_at"] < now:
            return None

        # Update last_used_at (fire and forget — non-blocking)
        self._touch_last_used(key_hash)

        return record

    def _touch_last_used(self, key_hash: str) -> None:
        """Update last_used_at timestamp. Non-critical — silent on failure."""
        try:
            with self.engine.begin() as conn:
                conn.execute(
                    text(
                        "UPDATE api_keys SET last_used_at = now() WHERE key_hash = :key_hash"
                    ),
                    {"key_hash": key_hash},
                )
        except Exception:
            # Don't break auth if this fails; log at debug for diagnostics.
            logger.debug("Failed to update last_used_at", exc_info=True)

    def list_keys(self) -> list[dict[str, Any]]:
        """List all API keys (metadata only — never returns hashes or plaintext).

        Includes ``connection_count`` via LEFT JOIN on system_connections.
        """
        with self.engine.begin() as conn:
            result = conn.execute(
                text("""
                    SELECT k.id, k.name, k.key_prefix, k.scopes, k.is_active,
                           k.created_at, k.expires_at, k.revoked_at, k.last_used_at,
                           COALESCE(COUNT(sc.id), 0) AS connection_count
                    FROM api_keys k
                    LEFT JOIN system_connections sc ON sc.api_key_id = k.id
                    GROUP BY k.id
                    ORDER BY k.created_at DESC
                """)
            )
            return [dict(r) for r in result.mappings().fetchall()]

    def get_key(self, key_id: UUID) -> dict[str, Any] | None:
        """Get a single key's metadata by ID."""
        with self.engine.begin() as conn:
            result = conn.execute(
                text("""
                    SELECT id, name, key_prefix, scopes, is_active,
                           created_at, expires_at, revoked_at, last_used_at
                    FROM api_keys
                    WHERE id = :key_id
                """),
                {"key_id": str(key_id)},
            )
            row = result.mappings().fetchone()
            return dict(row) if row else None

    def revoke_key(self, key_id: UUID) -> bool:
        """Revoke an API key by setting revoked_at."""
        with self.engine.begin() as conn:
            result = conn.execute(
                text("""
                    UPDATE api_keys
                    SET revoked_at = now(), is_active = FALSE
                    WHERE id = :key_id AND revoked_at IS NULL
                    RETURNING id
                """),
                {"key_id": str(key_id)},
            )
            row = result.fetchone()

        if row:
            logger.info("API key revoked: id=%s", key_id)
            return True
        return False

    def rotate_key(self, key_id: UUID) -> dict[str, Any] | None:
        """Rotate an API key: revoke old, create new with same name/scopes."""
        old = self.get_key(key_id)
        if old is None:
            return None

        # Revoke old key
        self.revoke_key(key_id)

        # Create new key with same config
        return self.create_key(
            name=old["name"],
            scopes=old["scopes"],
            expires_at=old.get("expires_at"),
        )

    # ------------------------------------------------------------------
    # Bootstrap
    # ------------------------------------------------------------------

    def bootstrap_from_env(self, master_key: str) -> dict[str, Any] | None:
        """Register a master key from environment variable if not already present.

        This allows zero-touch deployment: set AUTH_MASTER_KEY in Railway env
        and the first boot creates the admin key.
        """
        key_hash = self.hash_key(master_key)

        # Check if already registered
        with self.engine.begin() as conn:
            result = conn.execute(
                text("SELECT id FROM api_keys WHERE key_hash = :key_hash"),
                {"key_hash": key_hash},
            )
            if result.fetchone():
                logger.info("Master key already registered, skipping bootstrap")
                return None

        # Register with admin scopes
        import json

        key_prefix = self.get_prefix(master_key)
        admin_scopes = ["admin", "agents:run", "teams:run", "workflows:run"]

        with self.engine.begin() as conn:
            result = conn.execute(
                text("""
                    INSERT INTO api_keys (name, key_hash, key_prefix, scopes)
                    VALUES (:name, :key_hash, :key_prefix, CAST(:scopes AS jsonb))
                    RETURNING id, name, key_prefix, scopes, is_active, created_at
                """),
                {
                    "name": "master",
                    "key_hash": key_hash,
                    "key_prefix": key_prefix,
                    "scopes": json.dumps(admin_scopes),
                },
            )
            row = result.mappings().fetchone()

        logger.info("Master key bootstrapped: prefix=%s", key_prefix)
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # OS_SECURITY_KEY fallback
    # ------------------------------------------------------------------

    @staticmethod
    def verify_legacy_key(token: str, os_security_key: str) -> bool:
        """Constant-time comparison for the legacy OS_SECURITY_KEY."""
        return hmac.compare_digest(token, os_security_key)
