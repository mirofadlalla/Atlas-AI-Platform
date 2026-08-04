"""
scripts/backfill_qdrant_indexes.py
===================================
One-shot script to create payload indexes on an **existing** Qdrant collection.

Run this once after deploying the index changes to ensure any collection that
was created before the ``ensure_payload_indexes()`` method existed also gets
the correct indexes.

Usage (from the project root):
    python scripts/backfill_qdrant_indexes.py

    # Or target a specific collection:
    python scripts/backfill_qdrant_indexes.py --collection my_collection

    # Or target all collections:
    python scripts/backfill_qdrant_indexes.py --all
"""

import argparse
import logging
import sys
from pathlib import Path

# Make the project root importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.repositories.qdrant import QdrantRepository
from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("backfill_qdrant_indexes")


def backfill(collection_name: str) -> None:
    logger.info("Connecting to Qdrant at %s …", settings.qdrant_url)
    repo = QdrantRepository()

    if not repo.client.collection_exists(collection_name):
        logger.error("Collection '%s' does not exist. Skipping.", collection_name)
        return

    logger.info("Creating payload indexes on collection '%s' …", collection_name)
    repo.ensure_payload_indexes(collection_name)
    logger.info("✅ Done — collection '%s'", collection_name)


def backfill_all() -> None:
    repo = QdrantRepository()
    collections = repo.list_collections()
    if not collections:
        logger.warning("No collections found in Qdrant.")
        return

    logger.info("Found %d collection(s): %s", len(collections), collections)
    for col in collections:
        backfill(col)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill Qdrant payload indexes.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--collection",
        default=settings.qdrant_collection_name,
        help="Name of a single collection to index (default: from config).",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="Index ALL collections in the Qdrant instance.",
    )
    args = parser.parse_args()

    if args.all:
        backfill_all()
    else:
        backfill(args.collection)
