"""
crawler/tasks.py
─────────────────────────────────────────────────────────────────────────────
On-demand crawl task — called by POST /crawl API endpoint.

No external task queue is needed. The crawler runs:
  • Once automatically on startup  (docker compose → crawler service)
  • On-demand via POST /crawl      (runs in a background asyncio task)

The POST /crawl endpoint calls run_crawl() which launches the crawl in a
fire-and-forget asyncio task so the HTTP response returns immediately.
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

_running_tasks: set[asyncio.Task] = set()


async def _do_crawl(
    job_id: str,
    sources: list[str] | None,
    direct_urls: list[str] | None,
) -> None:
    """
    Core async crawl coroutine. Creates a job record, runs the crawl,
    updates the record on completion. Never raises — errors are logged.
    """
    from crawler.card_crawler import run_crawl_job
    from crawler.sources import BANK_SOURCE_KEYS
    from db.connection import get_db

    # Nothing specified → crawl every bank (listing discovery + known pages)
    crawl_sources = sources or ([] if direct_urls else BANK_SOURCE_KEYS)
    crawl_urls = direct_urls or []

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

    try:
        await run_crawl_job(job_id=job_id, sources=crawl_sources, direct_urls=crawl_urls)
        logger.info("On-demand crawl complete — job_id=%s", job_id)
    except Exception as exc:
        logger.error("On-demand crawl failed — job_id=%s: %s", job_id, exc)
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


def run_crawl(
    job_id: str,
    sources: list[str] | None = None,
    direct_urls: list[str] | None = None,
) -> None:
    """
    Launch an on-demand crawl in a background asyncio task.
    Called by POST /crawl — returns immediately, crawl runs in background.

    Inside FastAPI's async context: scheduled as a background task on the
    running event loop.
    In a plain script: asyncio.run() is used directly.
    """
    try:
        loop = asyncio.get_running_loop()
        task = loop.create_task(_do_crawl(job_id, sources, direct_urls))
        # Keep a reference so the task isn't garbage-collected mid-crawl
        _running_tasks.add(task)
        task.add_done_callback(_running_tasks.discard)
        logger.info("Crawl job %s scheduled as background task", job_id)
    except RuntimeError:
        asyncio.run(_do_crawl(job_id, sources, direct_urls))
