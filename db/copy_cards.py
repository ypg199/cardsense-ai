"""
db/copy_cards.py
─────────────────────────────────────────────────────────────────────────────
Copy the credit_cards catalogue (with its embeddings) from one MongoDB to
another, e.g. from a local database to MongoDB Atlas before going live.
Cards are upserted by _id, so it is safe to run again.

Usage:
    python -m db.copy_cards --source mongodb://localhost:27017 --target "mongodb+srv://..."
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import logging

from pymongo import MongoClient, ReplaceOne
from pymongo.collection import Collection

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")
logger = logging.getLogger(__name__)

COLLECTION = "credit_cards"
BATCH_SIZE = 100


def copy_cards(source: Collection, target: Collection) -> int:
    """Upsert every card from source into target; returns how many were copied."""
    copied = 0
    batch: list[ReplaceOne] = []
    for doc in source.find():
        batch.append(ReplaceOne({"_id": doc["_id"]}, doc, upsert=True))
        if len(batch) >= BATCH_SIZE:
            target.bulk_write(batch, ordered=False)
            copied += len(batch)
            batch = []
    if batch:
        target.bulk_write(batch, ordered=False)
        copied += len(batch)
    return copied


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy the card catalogue between MongoDB databases")
    parser.add_argument("--source", required=True, help="Source connection string")
    parser.add_argument("--target", required=True, help="Target connection string")
    parser.add_argument("--source-db", default="cardsense")
    parser.add_argument("--target-db", default="cardsense")
    args = parser.parse_args()

    with MongoClient(args.source) as src, MongoClient(args.target) as dst:
        count = copy_cards(src[args.source_db][COLLECTION], dst[args.target_db][COLLECTION])
    logger.info("Copied %d cards into %s.%s", count, args.target_db, COLLECTION)


if __name__ == "__main__":
    main()
