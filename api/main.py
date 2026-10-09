"""
api/main.py
─────────────────────────────────────────────────────────────────────────────
FastAPI application entry point for CardSense AI.

Start with:
    uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

Features
────────
- Lifespan context: DB ping on startup, graph pre-warm, graceful shutdown
- CORS for React dev server (localhost:3000 / localhost:5173)
- Global exception handlers (HTTP 422 / 404 / 500)
- All routers mounted: /session, /cards, /crawl
- Health check at GET /health
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Lifespan
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup / shutdown hooks.
    Startup:
      1. Ping MongoDB — log warning (don't crash) if unreachable.
      2. Pre-compile the LangGraph pipeline so the first request is fast.
    Shutdown:
      1. Close the Motor client cleanly.
    """
    # ── Startup ──────────────────────────────────────────────────────
    logger.info("=== CardSense API starting ===")

    # MongoDB connectivity check
    try:
        from db.connection import ping_db
        ok = await ping_db()
        if not ok:
            logger.warning("MongoDB ping failed — DB features may be unavailable")
    except Exception as exc:
        logger.warning("MongoDB ping error: %s", exc)

    # Ensure the sessions TTL index exists so statement data expires
    try:
        from db.connection import get_db
        from db.setup_indexes import create_sessions_indexes
        await create_sessions_indexes(get_db())
    except Exception as exc:
        logger.warning("Could not ensure sessions TTL index: %s", exc)

    # Pre-warm LangGraph (imports + compilation)
    try:
        from agents.graph import get_compiled_graph
        get_compiled_graph()
        logger.info("LangGraph pipeline compiled and ready")
    except Exception as exc:
        logger.warning("LangGraph pre-warm failed: %s", exc)

    logger.info("=== CardSense API ready ===")

    yield   # Application runs here

    # ── Shutdown ─────────────────────────────────────────────────────
    logger.info("=== CardSense API shutting down ===")
    try:
        from db.connection import close_db
        await close_db()
        logger.info("MongoDB client closed")
    except Exception as exc:
        logger.warning("Error closing MongoDB client: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="CardSense AI",
    description="Indian credit card benefit analyser — upload statements, score your utilization, find better cards.",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────────────────────
_cors_origins = [
    "http://localhost:3000",    # React dev (Vite default)
    "http://localhost:5173",    # Vite alternative
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]
# Deployed frontend origins come from ALLOWED_ORIGINS (comma-separated)
from api.settings import ALLOWED_ORIGINS
_cors_origins.extend(ALLOWED_ORIGINS)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# Global exception handlers
# ─────────────────────────────────────────────────────────────────────────────

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "status_code": exc.status_code},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error. Please try again.",
            "status_code": 500,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Routers
# ─────────────────────────────────────────────────────────────────────────────

from api.routes.session import router as session_router
from api.routes.cards import router as cards_router
from api.routes.crawl import router as crawl_router

app.include_router(session_router)
app.include_router(cards_router)
app.include_router(crawl_router)


# ─────────────────────────────────────────────────────────────────────────────
# Health check
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["meta"])
async def health():
    """Liveness probe."""
    return {"status": "ok", "service": "cardsense-api"}


@app.get("/", tags=["meta"])
async def root():
    return {
        "service": "CardSense AI",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }
