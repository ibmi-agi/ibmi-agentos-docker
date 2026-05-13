"""
Shared SQLAlchemy Engine
========================

Single connection pool shared across agents, teams, workflows, and
auth/connection services. One engine per process — sized to serve the
AgentOS API concurrently rather than each component getting its own pool.
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from db.url import db_url


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Return a cached SQLAlchemy engine with connection pooling."""
    return create_engine(
        db_url,
        pool_pre_ping=True,
        pool_recycle=3600,
        pool_size=10,
        max_overflow=20,
    )
