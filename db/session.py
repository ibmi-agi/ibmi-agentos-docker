"""
Database Session
================

PostgreSQL connection helpers.
``get_postgres_db()`` for agent storage backed by Postgres.
``create_knowledge()`` for agent knowledge backed by PgVector.

Embedder is OpenAI (``text-embedding-3-small`` by default). Set
``OPENAI_API_KEY`` in ``.env`` — the model can be overridden with
``EMBEDDING_MODEL``.
"""

from __future__ import annotations

from os import getenv
from typing import Any

from agno.db.postgres import PostgresDb
from agno.knowledge import Knowledge
from agno.vectordb.pgvector import PgVector, SearchType

from db.url import db_url

DB_ID = "agentos-db"


def get_postgres_db(contents_table: str | None = None) -> PostgresDb:
    """Create a PostgresDb instance.

    Pass ``contents_table`` only when this database is the ``contents_db``
    of a Knowledge base — it tells agno where to persist document contents.
    For plain agent persistence (sessions, memory) leave it unset.
    """
    if contents_table is not None:
        return PostgresDb(id=DB_ID, db_url=db_url, knowledge_table=contents_table)
    return PostgresDb(id=DB_ID, db_url=db_url)


def get_embedder() -> Any:
    """OpenAI embedder. Reads ``EMBEDDING_MODEL`` (default ``text-embedding-3-small``)."""
    from agno.knowledge.embedder.openai import OpenAIEmbedder

    model_id = getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    return OpenAIEmbedder(id=model_id)


def create_knowledge(name: str, table_name: str) -> Knowledge:
    """PgVector knowledge base with hybrid search.

    Plug into an Agent's ``knowledge=`` to give it a RAG surface. Vectors
    land in ``table_name``; document contents in ``{table_name}_contents``.
    """
    return Knowledge(
        name=name,
        vector_db=PgVector(
            db_url=db_url,
            table_name=table_name,
            search_type=SearchType.hybrid,
            embedder=get_embedder(),
        ),
        contents_db=get_postgres_db(contents_table=f"{table_name}_contents"),
    )
