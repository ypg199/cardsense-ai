"""
api/routes/cards.py
─────────────────────────────────────────────────────────────────────────────
Card catalogue endpoints.

GET /cards                — paginated list with optional filters
GET /cards/search?q=      — text search on name + bank + tags
GET /cards/{card_id}      — single card detail
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, HTTPException, Query, status

from api.models import CardDetailOut, CardListResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cards", tags=["cards"])

# Fields to always exclude from card responses (embedding is huge + internal)
_EXCLUDE_FIELDS = {"embedding": 0, "embedding_text": 0}


def _sanitise_card_doc(doc: dict) -> dict:
    """
    Coerce None / missing values to safe defaults before Pydantic validation.
    Handles documents written by the crawler that may have partial data.
    """
    # Top-level string fields that must not be None
    for field, default in [("network", "Unknown"), ("card_type", "cashback"),
                            ("name", ""), ("bank", "")]:
        if not doc.get(field):
            doc[field] = default

    # annual_fee / joining_fee must be int
    for field in ("annual_fee", "joining_fee"):
        val = doc.get(field)
        try:
            doc[field] = int(val) if val is not None else 0
        except (TypeError, ValueError):
            doc[field] = 0

    # Sanitise each benefit sub-document
    sanitised_benefits = []
    for b in doc.get("benefits", []) or []:
        if not isinstance(b, dict):
            continue
        # rate must be a float > 0; default 0.0 if None/missing
        try:
            b["rate"] = float(b["rate"]) if b.get("rate") is not None else 0.0
        except (TypeError, ValueError):
            b["rate"] = 0.0
        # reward_type must be a string
        if not b.get("reward_type"):
            b["reward_type"] = "cashback"
        # category / label must be strings
        if not b.get("category"):
            b["category"] = "others"
        if not b.get("label"):
            b["label"] = b.get("category", "")
        # merchant_keywords must be a list
        if not isinstance(b.get("merchant_keywords"), list):
            b["merchant_keywords"] = []
        sanitised_benefits.append(b)
    doc["benefits"] = sanitised_benefits

    # Ensure list fields are lists
    for field in ("best_for_tags", "not_good_for", "utilization_questions"):
        if not isinstance(doc.get(field), list):
            doc[field] = []

    return doc


# ─────────────────────────────────────────────────────────────────────────────
# GET /cards
# ─────────────────────────────────────────────────────────────────────────────

@router.get("", response_model=CardListResponse)
async def list_cards(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    card_type: str | None = Query(None, description="Filter by card_type"),
    bank: str | None = Query(None, description="Filter by bank name"),
):
    """
    Return a paginated list of cards.
    Excludes embedding vectors from results.
    """
    try:
        from db.connection import get_db
        db = get_db()

        query: dict = {}
        if card_type:
            query["card_type"] = card_type
        if bank:
            query["bank"] = {"$regex": re.escape(bank), "$options": "i"}

        total = await db["credit_cards"].count_documents(query)
        cursor = db["credit_cards"].find(query, _EXCLUDE_FIELDS).skip(skip).limit(limit)
        docs = await cursor.to_list(length=limit)

        cards = [CardDetailOut(**_sanitise_card_doc(doc)) for doc in docs]
        return CardListResponse(count=total, cards=cards)

    except Exception as exc:
        logger.error("list_cards error: %s", exc)
        raise HTTPException(status_code=500, detail="Could not load cards.")


# ─────────────────────────────────────────────────────────────────────────────
# GET /cards/search?q=
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/search", response_model=CardListResponse)
async def search_cards(
    q: str = Query(..., min_length=1, description="Search query"),
):
    """
    Full-text search on card name, bank, and best_for_tags.
    Returns top 20 matches. Requires the text index from setup_indexes.py.
    """
    try:
        from db.connection import get_db
        db = get_db()

        # Try Atlas text search first
        try:
            cursor = db["credit_cards"].find(
                {"$text": {"$search": q}},
                {**_EXCLUDE_FIELDS, "score": {"$meta": "textScore"}},
            ).sort([("score", {"$meta": "textScore"})]).limit(20)
            docs = await cursor.to_list(length=20)
        except Exception:
            # Fallback: regex search on name and bank
            regex = {"$regex": re.escape(q), "$options": "i"}
            cursor = db["credit_cards"].find(
                {"$or": [{"name": regex}, {"bank": regex}, {"best_for_tags": regex}]},
                _EXCLUDE_FIELDS,
            ).limit(20)
            docs = await cursor.to_list(length=20)

        # Remove the meta score field before parsing
        for doc in docs:
            doc.pop("score", None)

        cards = [CardDetailOut(**_sanitise_card_doc(doc)) for doc in docs]
        return CardListResponse(count=len(cards), cards=cards)

    except Exception as exc:
        logger.error("search_cards error: %s", exc)
        raise HTTPException(status_code=500, detail="Search failed.")


# ─────────────────────────────────────────────────────────────────────────────
# GET /cards/{card_id}
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{card_id}", response_model=CardDetailOut)
async def get_card(card_id: str):
    """Return a single card by slug ID. Excludes embedding vectors."""
    try:
        from db.connection import get_db
        db = get_db()

        doc = await db["credit_cards"].find_one({"_id": card_id}, _EXCLUDE_FIELDS)
        if doc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Card '{card_id}' not found.",
            )
        return CardDetailOut(**_sanitise_card_doc(doc))

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_card error (%s): %s", card_id, exc)
        raise HTTPException(status_code=500, detail="Could not load cards.")
