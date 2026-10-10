"""
api/settings.py
─────────────────────────────────────────────────────────────────────────────
Runtime limits and security settings, read from the environment once.
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


# Shared secret for admin endpoints (POST /crawl). Unset → admin endpoints disabled.
ADMIN_API_KEY: str = os.getenv("ADMIN_API_KEY", "")

# Upload limits for statement PDFs
MAX_UPLOAD_MB: int = _int_env("MAX_UPLOAD_MB", 10)
MAX_UPLOAD_BYTES: int = MAX_UPLOAD_MB * 1024 * 1024
MAX_FILES_PER_REQUEST: int = _int_env("MAX_FILES_PER_REQUEST", 12)

# Sessions (statement text, transactions) are deleted after this many hours
SESSION_TTL_HOURS: int = _int_env("SESSION_TTL_HOURS", 24)

# Extra CORS origins, comma-separated (e.g. https://card-sense.app)
ALLOWED_ORIGINS: list[str] = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]

# Optional regex for extra CORS origins, e.g. Cloudflare Pages preview builds:
# ^https://([a-z0-9-]+\.)?cardsense\.pages\.dev$
ALLOWED_ORIGIN_REGEX: str | None = os.getenv("ALLOWED_ORIGIN_REGEX") or None

# Statement analyses (uploads and sample runs) each client may start per hour.
# 0 turns the limit off.
RATE_LIMIT_PER_HOUR: int = _int_env("RATE_LIMIT_PER_HOUR", 0)
