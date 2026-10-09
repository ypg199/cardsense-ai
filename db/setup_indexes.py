"""
db/setup_indexes.py
Run ONCE to create all required MongoDB indexes for CardSense AI.

Usage:
    python -m db.setup_indexes

Idempotent: safe to run multiple times — existing indexes are not dropped.
"""

import asyncio
import logging

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, TEXT

from db.connection import close_db, get_db, ping_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Index definitions
# ─────────────────────────────────────────────


async def create_credit_cards_indexes(db: AsyncIOMotorDatabase) -> None:
    col = db["credit_cards"]

    # Text search: name + bank + tags
    await col.create_index(
        [("name", TEXT), ("bank", TEXT), ("best_for_tags", TEXT)],
        name="credit_cards_text_search",
        default_language="english",
    )
    logger.info("  [credit_cards] text search index ✓")

    # Filter by card_type and bank
    await col.create_index([("card_type", ASCENDING)], name="credit_cards_card_type")
    await col.create_index([("bank", ASCENDING)], name="credit_cards_bank")
    logger.info("  [credit_cards] card_type + bank indexes ✓")

    # Crawl freshness
    await col.create_index([("last_crawled", ASCENDING)], name="credit_cards_last_crawled")
    logger.info("  [credit_cards] last_crawled index ✓")

    # ── Atlas Vector Search index (768-dim text-embedding-004) ──
    # NOTE: Atlas Vector Search indexes CANNOT be created via the driver.
    #       Create this manually in the Atlas UI (or via Atlas CLI) with:
    #
    #   Collection : cardsense.credit_cards
    #   Index name : credit_cards_embedding_index
    #   Field      : embedding
    #   Dimensions : 768
    #   Similarity : cosine
    #
    # The compare_node will use $vectorSearch with this index name.
    # Without the Atlas index, compare_node falls back to category filtering.
    logger.info(
        "  [credit_cards] ⚠  Vector Search index must be created manually in Atlas UI "
        "(name: credit_cards_embedding_index, field: embedding, dims: 768, cosine)"
    )


async def create_sessions_indexes(db: AsyncIOMotorDatabase) -> None:
    col = db["sessions"]

    # TTL: each session document carries an `expires_at` Date (set on every
    # save), and MongoDB deletes it once that time passes. TTL indexes only
    # work on BSON Date fields, which is why `created_at` (an ISO string)
    # can't be used here.
    await col.create_index(
        [("expires_at", ASCENDING)],
        name="sessions_expires_at_ttl",
        expireAfterSeconds=0,
    )
    logger.info("  [sessions] TTL index on expires_at ✓")

    # Quick lookup by status (for admin queries)
    await col.create_index([("status", ASCENDING)], name="sessions_status")
    logger.info("  [sessions] status index ✓")


async def create_crawl_jobs_indexes(db: AsyncIOMotorDatabase) -> None:
    col = db["crawl_jobs"]

    await col.create_index([("created_at", ASCENDING)], name="crawl_jobs_created_at")
    await col.create_index([("status", ASCENDING)], name="crawl_jobs_status")
    logger.info("  [crawl_jobs] created_at + status indexes ✓")


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────


async def setup_all_indexes() -> None:
    logger.info("=== CardSense AI — MongoDB Index Setup ===")

    ok = await ping_db()
    if not ok:
        logger.error("Cannot reach MongoDB. Aborting.")
        return

    db = get_db()
    logger.info("Connected to database: %s", db.name)

    logger.info("Creating indexes for [credit_cards] …")
    await create_credit_cards_indexes(db)

    logger.info("Creating indexes for [sessions] …")
    await create_sessions_indexes(db)

    logger.info("Creating indexes for [crawl_jobs] …")
    await create_crawl_jobs_indexes(db)

    logger.info("=== Index setup complete ✅ ===")
    await close_db()


if __name__ == "__main__":
    asyncio.run(setup_all_indexes())
