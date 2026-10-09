"""
crawler/run.py
─────────────────────────────────────────────────────────────────────────────
One-shot crawler entrypoint.

Runs once on startup (via docker compose), crawls all sources and direct
bank URLs, upserts cards to MongoDB, then exits.

Usage:
    python -m crawler.run                    # crawl everything
    python -m crawler.run --sources cardinsider bankbazaar
    python -m crawler.run --urls https://...
    python -m crawler.run --seed-only        # skip crawl, just seed 5 test cards
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import uuid
from datetime import UTC, datetime

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger(__name__)


async def main(
    sources: list[str] | None = None,
    direct_urls: list[str] | None = None,
    seed_only: bool = False,
) -> int:
    """
    Run the one-shot crawl job.
    Returns exit code: 0 = success, 1 = failure.
    """
    from db.connection import close_db, get_db, ping_db

    # ── 1. DB connectivity ────────────────────────────────────────────────────
    logger.info("=== CardSense Crawler — one-shot run ===")
    ok = await ping_db()
    if not ok:
        logger.error("Cannot reach MongoDB — check MONGODB_URI in .env")
        return 1

    # ── 2. Always seed the 5 test cards first ─────────────────────────────────
    logger.info("Seeding 5 canonical test cards…")
    try:
        from db.seed import seed_cards

        await seed_cards()
    except Exception as exc:
        logger.warning("Seed failed (non-fatal): %s", exc)

    if seed_only:
        logger.info("--seed-only flag set — skipping web crawl.")
        await close_db()
        return 0

    # ── 3. Determine what to crawl ────────────────────────────────────────────
    from crawler.sources import BANK_SOURCE_KEYS

    # Nothing specified → crawl every bank (listing discovery + known pages)
    crawl_sources = sources or ([] if direct_urls else BANK_SOURCE_KEYS)
    crawl_urls = direct_urls or []

    logger.info("Sources to crawl : %s", crawl_sources or "(none)")
    logger.info("Direct URLs      : %d URLs", len(crawl_urls))

    # ── 4. Create a job record in MongoDB ────────────────────────────────────
    job_id = str(uuid.uuid4())
    db = get_db()
    try:
        await db["crawl_jobs"].insert_one(
            {
                "_id": job_id,
                "status": "running",
                "sources": crawl_sources,
                "direct_urls": crawl_urls,
                "cards_upserted": 0,
                "cards_failed": 0,
                "errors": [],
                "created_at": datetime.now(UTC).isoformat(),
                "finished_at": None,
            }
        )
    except Exception as exc:
        logger.warning("Could not create crawl_jobs record: %s", exc)

    # ── 5. Run the crawl ──────────────────────────────────────────────────────
    try:
        from crawler.card_crawler import run_crawl_job

        await run_crawl_job(
            job_id=job_id,
            sources=crawl_sources,
            direct_urls=crawl_urls,
        )
        logger.info("=== Crawl complete. Exiting. ===")
        await close_db()
        return 0

    except Exception as exc:
        logger.error("Crawl failed: %s", exc)
        try:
            await db["crawl_jobs"].update_one(
                {"_id": job_id},
                {
                    "$set": {
                        "status": "failed",
                        "errors": [str(exc)],
                        "finished_at": datetime.now(UTC).isoformat(),
                    }
                },
            )
        except Exception:
            pass
        await close_db()
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CardSense one-shot card crawler")
    parser.add_argument(
        "--sources",
        nargs="*",
        help="Source keys to crawl (default: every bank). E.g. --sources axis hdfc, or an aggregator",
    )
    parser.add_argument(
        "--urls",
        nargs="*",
        dest="direct_urls",
        help="Direct card page URLs to crawl",
    )
    parser.add_argument(
        "--seed-only",
        action="store_true",
        help="Skip web crawl — only seed the 5 test cards",
    )
    args = parser.parse_args()

    exit_code = asyncio.run(
        main(
            sources=args.sources,
            direct_urls=args.direct_urls,
            seed_only=args.seed_only,
        )
    )
    sys.exit(exit_code)
