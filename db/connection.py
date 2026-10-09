"""
db/connection.py
Motor async MongoDB client singleton.
Usage:
    from db.connection import get_db, get_client
    db = await get_db()
"""

import logging
import os

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

load_dotenv()

logger = logging.getLogger(__name__)

# Module-level singleton — created once per process
_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None

MONGODB_URI: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DB_NAME: str = os.getenv("MONGODB_DB_NAME", "cardsense")


def get_client() -> AsyncIOMotorClient:
    """Return (or create) the Motor client singleton."""
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(
            MONGODB_URI,
            serverSelectionTimeoutMS=10_000,
            connectTimeoutMS=10_000,
        )
        logger.info("MongoDB client created → %s / %s", MONGODB_URI.split("@")[-1], DB_NAME)
    return _client


def get_db() -> AsyncIOMotorDatabase:
    """Return the database handle (creates client if needed)."""
    global _db
    if _db is None:
        _db = get_client()[DB_NAME]
    return _db


async def ping_db() -> bool:
    """
    Verify connectivity by running the 'ping' admin command.
    Returns True on success, False on failure.
    """
    try:
        client = get_client()
        await client.admin.command("ping")
        logger.info("✅ MongoDB ping OK")
        return True
    except Exception as exc:
        logger.error("❌ MongoDB ping failed: %s", exc)
        return False


async def close_db() -> None:
    """Close the Motor client (call during application shutdown)."""
    global _client, _db
    if _client is not None:
        _client.close()
        _client = None
        _db = None
        logger.info("MongoDB client closed")
