"""
api/rate_limit.py
─────────────────────────────────────────────────────────────────────────────
Per-client limit on the endpoints that start AI work (statement uploads and
the sample run), so a public demo can't run up the Gemini bill.

A sliding one-hour window kept in process memory. That is per instance, which
is enough for a demo capped at a couple of instances; a shared store would be
needed beyond that. RATE_LIMIT_PER_HOUR=0 (the default) turns it off.
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from api import settings

WINDOW_SECONDS = 3600

_hits: dict[str, deque[float]] = defaultdict(deque)


def _client_key(request: Request) -> str:
    # uvicorn runs with --proxy-headers, so request.client is the real caller
    # behind Cloud Run / Render's load balancer
    return request.client.host if request.client else "unknown"


def check_rate_limit(request: Request) -> None:
    """FastAPI dependency: 429 once a client exceeds RATE_LIMIT_PER_HOUR."""
    limit = settings.RATE_LIMIT_PER_HOUR
    if limit <= 0:
        return
    now = time.monotonic()
    hits = _hits[_client_key(request)]
    while hits and now - hits[0] >= WINDOW_SECONDS:
        hits.popleft()
    if len(hits) >= limit:
        retry_after = int(WINDOW_SECONDS - (now - hits[0])) + 1
        raise HTTPException(
            status_code=429,
            detail="You've analysed a lot of statements in the last hour. Please try again a little later.",
            headers={"Retry-After": str(retry_after)},
        )
    hits.append(now)


def reset() -> None:
    """Clear all counters (tests)."""
    _hits.clear()
