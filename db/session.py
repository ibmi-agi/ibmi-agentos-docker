"""
Database Session
================

PostgreSQL connection helpers.
``get_postgres_db()`` for agent storage backed by Postgres.
``create_knowledge()`` for agent knowledge backed by PgVector.

Embedder choice is env-driven so the template ships offline-friendly
(local Ollama) but switches to OpenAI with one variable change:

    EMBEDDING_PROVIDER=ollama  EMBEDDING_MODEL=qwen3-embedding:0.6b   (default)
    EMBEDDING_PROVIDER=openai  EMBEDDING_MODEL=text-embedding-3-small
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
    """Build the embedder per ``EMBEDDING_PROVIDER`` + ``EMBEDDING_MODEL``.

    Defaults to local Ollama (``qwen3-embedding:0.6b``) so the template
    runs offline. The ``ollama`` service in ``compose.yaml`` pulls the
    model on first boot.
    """
    provider = getenv("EMBEDDING_PROVIDER", "ollama").lower()
    if provider == "ollama":
        from agno.knowledge.embedder.ollama import OllamaEmbedder

        model_id = getenv("EMBEDDING_MODEL", "qwen3-embedding:0.6b")
        host = getenv("OLLAMA_HOST", "http://localhost:11434")
        return OllamaEmbedder(id=model_id, host=host)
    if provider == "openai":
        from agno.knowledge.embedder.openai import OpenAIEmbedder

        model_id = getenv("EMBEDDING_MODEL", "text-embedding-3-small")
        return OpenAIEmbedder(id=model_id)
    raise ValueError(
        f"Unsupported EMBEDDING_PROVIDER={provider!r}. Use 'ollama' or 'openai'."
    )


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
