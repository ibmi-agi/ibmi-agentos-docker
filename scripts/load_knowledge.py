"""
Load Knowledge — ingest knowledge/{tables,queries,business} into PgVector.

Usage:
    uv run python scripts/load_knowledge.py             # upsert (skip existing)
    uv run python scripts/load_knowledge.py --recreate  # drop tables and reload

Run this after editing any file under ``knowledge/`` so the changes
land in the vector store. The embedder is OpenAI (``text-embedding-3-small``
by default — override with ``EMBEDDING_MODEL``).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

# Load .env before any agno imports so OPENAI_API_KEY / EMBEDDING_MODEL
# are visible when create_knowledge() runs.
load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = REPO_ROOT / "knowledge"
SUBDIRS = ("tables", "queries", "business")


def load_knowledge(recreate: bool = False) -> None:
    """Load knowledge files into the vector database.

    Args:
        recreate: Drop the PgVector table and reload from scratch.
                  Use after schema changes (e.g. swapping embedder dims).
    """
    # Deferred import — keeps the script's --help fast and avoids the
    # PgVector table-creation roundtrip when the user just wants the
    # usage screen.
    from app.knowledge import ibmi_knowledge

    if recreate:
        print("Recreating knowledge base (dropping existing data)...\n")
        if ibmi_knowledge.vector_db:
            ibmi_knowledge.vector_db.drop()
            ibmi_knowledge.vector_db.create()

    print(f"Loading knowledge from: {KNOWLEDGE_DIR}\n")

    for subdir in SUBDIRS:
        path = KNOWLEDGE_DIR / subdir
        if not path.exists():
            print(f"  {subdir}/: (directory not found, skipping)")
            continue

        files = [f for f in path.iterdir() if f.is_file() and not f.name.startswith(".")]
        print(f"  {subdir}/: {len(files)} file(s)")
        if files:
            ibmi_knowledge.insert(name=f"knowledge-{subdir}", path=str(path))

    print("\nDone.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load knowledge into PgVector")
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Drop existing knowledge and reload from scratch.",
    )
    args = parser.parse_args()
    load_knowledge(recreate=args.recreate)
