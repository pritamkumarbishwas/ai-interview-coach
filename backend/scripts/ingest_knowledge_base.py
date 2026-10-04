"""Ingest `data/knowledge_base/` (markdown/JSON) into Qdrant.

Usage (from backend/):

    python -m scripts.ingest_knowledge_base              # incremental upsert
    python -m scripts.ingest_knowledge_base --reset      # drop collections first
    python -m scripts.ingest_knowledge_base --path DIR   # custom knowledge base

Re-running is safe: chunk ids are derived from source + position, so points
are overwritten instead of duplicated.
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Support both `python -m scripts.ingest_knowledge_base` and direct execution.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import resolve_knowledge_base_dir, settings
from app.services.knowledge_loader import load_knowledge_base
from app.services.rag_service import rag_service


async def run(path: Path, reset: bool) -> int:
    grouped = load_knowledge_base(path)
    if reset:
        rag_service.delete_collections()
        print("Dropped existing collections.")
    if not grouped:
        print(f"No knowledge files found under {path}")
        return 0

    total = 0
    for collection in sorted(grouped):
        chunks = grouped[collection]
        count = await rag_service.upsert(collection, chunks)
        total += count
        print(f"  {collection}: {count} chunks")
    print(f"Ingested {total} chunks from {path}")
    print(
        f"Qdrant: {settings.qdrant_url} | RAG_ENABLED: {settings.rag_enabled} | "
        f"model: {settings.embedding_model}"
    )
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--path",
        type=Path,
        default=None,
        help="Knowledge base directory (default: KNOWLEDGE_BASE_DIR)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete all collections before ingesting",
    )
    args = parser.parse_args()
    path = (args.path or resolve_knowledge_base_dir()).resolve()
    asyncio.run(run(path, args.reset))


if __name__ == "__main__":
    main()
