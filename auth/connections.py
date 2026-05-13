"""
System Connections Service
==========================

CRUD operations for IBM i system connection records.

Each connection belongs to an API key and stores encrypted IBM i credentials.
Connections are used to obtain per-user MCP Bearer tokens at request time.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Engine

from auth.encryption import decrypt_credential, encrypt_credential
from db.engine import get_engine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Table DDL — idempotent, runs on first use
# ---------------------------------------------------------------------------

_CREATE_TABLE_SQL = text("""
CREATE TABLE IF NOT EXISTS system_connections (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    api_key_id      UUID NOT NULL REFERENCES api_keys(id) ON DELETE CASCADE,
    name            VARCHAR(255) NOT NULL,
    host            VARCHAR(255) NOT NULL,
    port            INTEGER NOT NULL DEFAULT 8076,
    ibmi_user       TEXT NOT NULL,
    ibmi_password   TEXT NOT NULL,
    is_default      BOOLEAN NOT NULL DEFAULT FALSE,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ,
    last_connected  TIMESTAMPTZ,
    UNIQUE(api_key_id, name)
)
""")

_CREATE_INDEX_SQL = text("""
CREATE INDEX IF NOT EXISTS idx_system_connections_api_key
ON system_connections (api_key_id)
""")

# Columns returned in non-credential queries
_SAFE_COLUMNS = (
    "id, api_key_id, name, host, port, ibmi_user,"
    " is_default, is_active, created_at, updated_at, last_connected"
)


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Convert a SQLAlchemy row mapping to a dict, excluding encrypted fields."""
    d = dict(row)
    d.pop("ibmi_password", None)
    if "ibmi_user" in d:
        try:
            d["ibmi_user"] = decrypt_credential(d["ibmi_user"])
        except Exception:
            d["ibmi_user"] = "***"
    return d


class ConnectionsService:
    """Manages IBM i system connection records."""

    def __init__(self, engine: Engine | None = None) -> None:
        self.engine = engine or get_engine()
        self._ensure_table()

    def _ensure_table(self) -> None:
        with self.engine.begin() as conn:
            conn.execute(_CREATE_TABLE_SQL)
            conn.execute(_CREATE_INDEX_SQL)

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create_connection(
        self,
        api_key_id: UUID,
        name: str,
        host: str,
        ibmi_user: str,
        ibmi_password: str,
        port: int = 8076,
        is_default: bool = False,
    ) -> dict[str, Any]:
        """Register a new IBM i system connection."""
        encrypted_user = encrypt_credential(ibmi_user)
        encrypted_password = encrypt_credential(ibmi_password)

        with self.engine.begin() as conn:
            # Atomically clear existing default + insert in one transaction
            if is_default:
                conn.execute(
                    text("""
                        UPDATE system_connections
                        SET is_default = FALSE
                        WHERE api_key_id = :api_key_id AND is_default = TRUE
                    """),
                    {"api_key_id": str(api_key_id)},
                )

            result = conn.execute(
                text(f"""
                    INSERT INTO system_connections
                        (api_key_id, name, host, port, ibmi_user, ibmi_password, is_default)
                    VALUES
                        (:api_key_id, :name, :host, :port, :ibmi_user, :ibmi_password, :is_default)
                    RETURNING {_SAFE_COLUMNS}
                """),
                {
                    "api_key_id": str(api_key_id),
                    "name": name,
                    "host": host,
                    "port": port,
                    "ibmi_user": encrypted_user,
                    "ibmi_password": encrypted_password,
                    "is_default": is_default,
                },
            )
            row = result.mappings().fetchone()

        record = _row_to_dict(row) if row else {}
        logger.info(
            "Connection created: name=%s host=%s api_key_id=%s", name, host, api_key_id
        )
        return record

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def list_all_connections(
        self, api_key_id: UUID | None = None
    ) -> list[dict[str, Any]]:
        """List all connections across all API keys (admin view).

        Includes ``api_key_name`` via LEFT JOIN on api_keys.
        Optionally filtered by *api_key_id*.
        """
        where = ""
        params: dict[str, str] = {}
        if api_key_id is not None:
            where = "WHERE sc.api_key_id = :api_key_id"
            params["api_key_id"] = str(api_key_id)

        sql = f"""
            SELECT sc.id, sc.api_key_id, sc.name, sc.host, sc.port, sc.ibmi_user,
                   sc.is_default, sc.is_active, sc.created_at, sc.updated_at,
                   sc.last_connected, k.name AS api_key_name
            FROM system_connections sc
            LEFT JOIN api_keys k ON k.id = sc.api_key_id
            {where}
            ORDER BY sc.created_at DESC
        """  # noqa: S608

        with self.engine.begin() as conn:
            result = conn.execute(text(sql), params)
            return [_row_to_dict(r) for r in result.mappings().fetchall()]

    def list_connections(self, api_key_id: UUID) -> list[dict[str, Any]]:
        """List all connections for an API key (credentials redacted)."""
        with self.engine.begin() as conn:
            result = conn.execute(
                text(f"""
                    SELECT {_SAFE_COLUMNS}
                    FROM system_connections
                    WHERE api_key_id = :api_key_id
                    ORDER BY is_default DESC, created_at DESC
                """),
                {"api_key_id": str(api_key_id)},
            )
            return [_row_to_dict(r) for r in result.mappings().fetchall()]

    def get_connection(
        self, connection_id: UUID, api_key_id: UUID
    ) -> dict[str, Any] | None:
        """Get a single connection by ID (scoped to API key)."""
        with self.engine.begin() as conn:
            result = conn.execute(
                text(f"""
                    SELECT {_SAFE_COLUMNS}
                    FROM system_connections
                    WHERE id = :id AND api_key_id = :api_key_id
                """),
                {"id": str(connection_id), "api_key_id": str(api_key_id)},
            )
            row = result.mappings().fetchone()
            return _row_to_dict(row) if row else None

    def get_connection_by_name(
        self, name: str, api_key_id: UUID
    ) -> dict[str, Any] | None:
        """Get a single connection by name (scoped to API key)."""
        with self.engine.begin() as conn:
            result = conn.execute(
                text(f"""
                    SELECT {_SAFE_COLUMNS}
                    FROM system_connections
                    WHERE api_key_id = :api_key_id AND name = :name
                    LIMIT 1
                """),
                {"api_key_id": str(api_key_id), "name": name},
            )
            row = result.mappings().fetchone()
            return _row_to_dict(row) if row else None

    def get_default_connection(self, api_key_id: UUID) -> dict[str, Any] | None:
        """Get the default connection for an API key."""
        with self.engine.begin() as conn:
            result = conn.execute(
                text(f"""
                    SELECT {_SAFE_COLUMNS}
                    FROM system_connections
                    WHERE api_key_id = :api_key_id AND is_default = TRUE AND is_active = TRUE
                    LIMIT 1
                """),
                {"api_key_id": str(api_key_id)},
            )
            row = result.mappings().fetchone()
            return _row_to_dict(row) if row else None

    def get_connection_credentials(
        self, connection_id: UUID, api_key_id: UUID
    ) -> dict[str, str] | None:
        """Get decrypted credentials for a connection."""
        with self.engine.begin() as conn:
            result = conn.execute(
                text("""
                    SELECT host, port, ibmi_user, ibmi_password
                    FROM system_connections
                    WHERE id = :id AND api_key_id = :api_key_id AND is_active = TRUE
                """),
                {"id": str(connection_id), "api_key_id": str(api_key_id)},
            )
            row = result.mappings().fetchone()

        if row is None:
            return None

        return {
            "host": row["host"],
            "port": str(row["port"]),
            "user": decrypt_credential(row["ibmi_user"]),
            "password": decrypt_credential(row["ibmi_password"]),
        }

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update_connection(
        self,
        connection_id: UUID,
        api_key_id: UUID,
        *,
        name: str | None = None,
        host: str | None = None,
        port: int | None = None,
        ibmi_user: str | None = None,
        ibmi_password: str | None = None,
    ) -> dict[str, Any] | None:
        """Update a connection's fields. Only non-None fields are updated."""
        sets: list[str] = ["updated_at = now()"]
        params: dict[str, Any] = {
            "id": str(connection_id),
            "api_key_id": str(api_key_id),
        }

        if name is not None:
            sets.append("name = :name")
            params["name"] = name
        if host is not None:
            sets.append("host = :host")
            params["host"] = host
        if port is not None:
            sets.append("port = :port")
            params["port"] = port
        if ibmi_user is not None:
            sets.append("ibmi_user = :ibmi_user")
            params["ibmi_user"] = encrypt_credential(ibmi_user)
        if ibmi_password is not None:
            sets.append("ibmi_password = :ibmi_password")
            params["ibmi_password"] = encrypt_credential(ibmi_password)

        sql = f"""
            UPDATE system_connections
            SET {", ".join(sets)}
            WHERE id = :id AND api_key_id = :api_key_id
            RETURNING {_SAFE_COLUMNS}
        """  # noqa: S608  — column names are hardcoded literals, not user input

        with self.engine.begin() as conn:
            result = conn.execute(text(sql), params)
            row = result.mappings().fetchone()
            return _row_to_dict(row) if row else None

    def set_default(self, connection_id: UUID, api_key_id: UUID) -> bool:
        """Set a connection as the default for its API key (atomic)."""
        with self.engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE system_connections
                    SET is_default = FALSE
                    WHERE api_key_id = :api_key_id AND is_default = TRUE
                """),
                {"api_key_id": str(api_key_id)},
            )
            result = conn.execute(
                text("""
                    UPDATE system_connections
                    SET is_default = TRUE, updated_at = now()
                    WHERE id = :id AND api_key_id = :api_key_id
                    RETURNING id
                """),
                {"id": str(connection_id), "api_key_id": str(api_key_id)},
            )
            return result.fetchone() is not None

    def touch_last_connected(
        self, connection_id: UUID, api_key_id: UUID | None = None
    ) -> None:
        """Update the last_connected timestamp."""
        try:
            sql = "UPDATE system_connections SET last_connected = now() WHERE id = :id"
            params: dict[str, str] = {"id": str(connection_id)}
            if api_key_id is not None:
                sql += " AND api_key_id = :api_key_id"
                params["api_key_id"] = str(api_key_id)
            with self.engine.begin() as conn:
                conn.execute(text(sql), params)
        except Exception:
            logger.debug("Failed to update last_connected for %s", connection_id)

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_connection(self, connection_id: UUID, api_key_id: UUID) -> bool:
        """Delete a connection."""
        with self.engine.begin() as conn:
            result = conn.execute(
                text("""
                    DELETE FROM system_connections
                    WHERE id = :id AND api_key_id = :api_key_id
                    RETURNING id
                """),
                {"id": str(connection_id), "api_key_id": str(api_key_id)},
            )
            deleted = result.fetchone() is not None

        if deleted:
            logger.info("Connection deleted: id=%s", connection_id)
        return deleted
