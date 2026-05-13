"""
Shared IBM i Knowledge Base
===========================

A single PgVector ``Knowledge`` instance shared by every agent that
declares ``knowledge=ibmi_knowledge, search_knowledge=True``. The
knowledge is seeded from files under ``knowledge/`` at the repo root:

    knowledge/tables/*.json     — table metadata (one file per table)
    knowledge/queries/*.sql     — validated example queries with header tags
    knowledge/business/*.md     — domain conventions, gotchas, metric definitions

Run ``uv run python scripts/load_knowledge.py`` to (re)ingest those files
into PgVector. Use ``--recreate`` to drop and reload from scratch.

Tables created on first use (auto by PgVector):
    ibmi_knowledge            — vectors + metadata
    ibmi_knowledge_contents   — full document content

The singleton is lazy on first attribute access (PEP 562) so importing
this module does not touch Postgres at import time — keeps unit tests
infra-free.
"""

from __future__ import annotations

from typing import Any

from db.session import create_knowledge

_ibmi_knowledge: Any = None


def __getattr__(name: str) -> Any:
    if name == "ibmi_knowledge":
        global _ibmi_knowledge
        if _ibmi_knowledge is None:
            _ibmi_knowledge = create_knowledge(
                name="IBM i Knowledge",
                table_name="ibmi_knowledge",
            )
        return _ibmi_knowledge
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
