"""
api/routes/crawl.py
─────────────────────────────────────────────────────────────────────────────
Admin crawl endpoints.

POST /crawl           — trigger a background Celery crawl job
GET  /crawl/jobs      — list last 20 crawl jobs with status
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException

from api import settings
from api.models import CrawlJobListResponse, CrawlJobResponse, CrawlJobStatusOut, CrawlRequest

logger = logging.getLogger(__name__)


async def require_admin_key(x_admin_key: str = Header(default="")) -> None:
    """Allow the request only if X-Admin-Key matches ADMIN_API_KEY."""
    if not settings.ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Admin endpoints are disabled.")
    if not secrets.compare_digest(x_admin_key, settings.ADMIN_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid admin key.")


router = APIRouter(prefix="/crawl", tags=["crawl"], dependencies=[Depends(require_admin_key)])


# ─────────────────────────────────────────────────────────────────────────────
# POST /crawl
# ─────────────────────────────────────────────────────────────────────────────

@router.post("", response_model=CrawlJobResponse, status_code=202)
async def trigger_crawl(body: CrawlRequest):
    """
    Admin endpoint (requires the X-Admin-Key header) — trigger a Celery background crawl job.

    Body (optional):
      sources:      list of source keys (e.g. ["cardinsider", "bankbazaar"])
      direct_urls:  list of specific card page URLs to crawl

    Returns a job_id that can be polled via GET /crawl/jobs.
    """
    job_id = str(uuid.uuid4())

    # Persist job record to MongoDB
    try:
        from db.connection import get_db
        db = get_db()
        await db["crawl_jobs"].insert_one({
            "_id": job_id,
            "status": "pending",
            "sources": body.sources or [],
            "direct_urls": body.direct_urls or [],
            "cards_upserted": 0,
            "cards_failed": 0,
            "errors": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": None,
        })
    except Exception as exc:
        logger.warning("Failed to persist crawl job to DB: %s", exc)

    # Launch crawl as a background asyncio task (no Celery needed)
    try:
        from crawler.tasks import run_crawl
        run_crawl(
            job_id=job_id,
            sources=body.sources,
            direct_urls=body.direct_urls,
        )
        logger.info("Crawl job %s started in background", job_id)
    except Exception as exc:
        logger.warning("Could not start crawl job %s: %s", job_id, exc)

    return CrawlJobResponse(
        job_id=job_id,
        message=f"Crawl job {job_id} submitted. Poll GET /crawl/jobs for status.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /crawl/jobs
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/jobs", response_model=CrawlJobListResponse)
async def list_crawl_jobs():
    """Return the last 20 crawl jobs sorted by creation time descending."""
    try:
        from db.connection import get_db
        db = get_db()
        cursor = db["crawl_jobs"].find(
            {},
            {"_id": 1, "status": 1, "cards_upserted": 1, "cards_failed": 1,
             "created_at": 1, "finished_at": 1},
        ).sort("created_at", -1).limit(20)

        docs = await cursor.to_list(length=20)
        jobs = [
            CrawlJobStatusOut(
                job_id=str(doc.get("_id", "")),
                status=doc.get("status", "unknown"),
                cards_upserted=doc.get("cards_upserted", 0),
                cards_failed=doc.get("cards_failed", 0),
                created_at=doc.get("created_at"),
                finished_at=doc.get("finished_at"),
            )
            for doc in docs
        ]
        return CrawlJobListResponse(jobs=jobs)

    except Exception as exc:
        logger.error("list_crawl_jobs error: %s", exc)
        raise HTTPException(status_code=500, detail="Could not load crawl jobs.")
