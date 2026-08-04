"""
Database Session
================

PostgreSQL database connection for AgentOS.
"""

from functools import cache

from agno.db.postgres import PostgresDb

from db.url import db_url

DB_ID = "agentos-db"


@cache
def get_postgres_db(contents_table: str | None = None) -> PostgresDb:
    """Returns the shared PostgresDb instance for the AgentOS.

    Memoized so every agent reuses the same object instead of constructing
    a fresh PostgresDb on each call.

    Args:
        contents_table: Optional table name for storing knowledge contents.

    Returns:
        Configured PostgresDb instance.
    """
    if contents_table is not None:
        return PostgresDb(id=DB_ID, db_url=db_url, knowledge_table=contents_table)
    return PostgresDb(id=DB_ID, db_url=db_url)
