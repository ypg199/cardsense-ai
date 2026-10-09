"""
agents/question_node.py
─────────────────────────────────────────────────────────────────────────────
Node 3: question_gen_node

Responsibilities
────────────────
1. Load the current card's document from MongoDB (benefits + utilization_questions).
2. Auto-detect answered questions by matching transaction merchants against
   benefit.merchant_keywords — mark those as answered=True without asking user.
3. Filter: only generate questions for categories where spend > 0 AND
   benefit rate > 1% AND not already auto-answered.
4. Enrich each utilization_question with detected_spend and potential_cashback.
5. Generate GENERAL usage questions (always added, up to 2-3).
6. Cap at 8 questions total. Sort by potential_cashback descending.
7. If pending questions remain → set current_question, interrupt (graph pauses).
8. If all answered → advance status to "calculating".

State fields read
─────────────────
  cards[current_card_idx].card_id
  cards[current_card_idx].transactions
  cards[current_card_idx].qa_answers
  cards[current_card_idx].pending_questions
  current_card_idx

State fields written
────────────────────
  cards[current_card_idx].pending_questions
  cards[current_card_idx].answered_questions
  cards[current_card_idx].qa_answers         (auto-answered entries added)
  cards[current_card_idx].status             "questioning" | "calculating"
  current_question                           next Question or None
  status                                     mirrors card status
  ui_action                                  "show_question" | "show_loading"
  total_questions_count
  answered_questions_count
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections import defaultdict
from copy import deepcopy
from typing import Any

from dotenv import load_dotenv

from agents.state import AnalysisState, CardState, Question, Transaction

load_dotenv()
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

MAX_QUESTIONS_PER_CARD = 8
MIN_BENEFIT_RATE = 0.01  # 1% — questions only for benefits above this
MIN_CATEGORY_SPEND = 0.01  # ₹0.01 — must have some spend in the category

# ── Exact prompt from Section 11 ─────────────────────────────────────────────
QUESTION_GEN_PROMPT = """\
Card: {card_name} by {card_bank}

Benefits: {benefits_json}

Detected spend categories: {category_spend_json}

Generate YES/NO questions to confirm which benefits the user actually used.
Only generate questions for categories with spend > 0 AND benefit rate > 1%.
Max 8 questions. Sort by potential_cashback descending.

Also add 2-3 general usage questions like:
'Do you use this as your primary card for daily expenses?'
'Do you always check the cashback offer before making a large purchase?'

Return ONLY JSON array:
[{{
  "id": "q_unique",
  "category": "category_key_or_general",
  "text": "Do you ... using this card?",
  "hint": "Earns X% cashback — ₹YYY potential this month",
  "detected_spend": 1200.0,
  "potential_cashback": 300.0,
  "is_general": false
}}]"""

# General questions used when Gemini is unavailable or as guaranteed additions
GENERAL_QUESTIONS: list[dict] = [
    {
        "id": "q_general_primary",
        "category": "general",
        "text": "Do you use this as your primary card for daily expenses?",
        "hint": "Using this card for all spends maximises your total cashback earned.",
        "detected_spend": 0.0,
        "potential_cashback": 0.0,
        "is_general": True,
    },
    {
        "id": "q_general_offers",
        "category": "general",
        "text": "Do you always check for cashback offers before making a large purchase?",
        "hint": "Checking offers before purchasing can unlock extra cashback.",
        "detected_spend": 0.0,
        "potential_cashback": 0.0,
        "is_general": True,
    },
    {
        "id": "q_general_autopay",
        "category": "general",
        "text": "Do you use this card for auto-pay on subscriptions (OTT, insurance, etc.)?",
        "hint": "Auto-pay subscriptions are an easy way to earn passive cashback.",
        "detected_spend": 0.0,
        "potential_cashback": 0.0,
        "is_general": True,
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# DB helpers (sync-compatible wrapper used inside the sync LangGraph node)
# ─────────────────────────────────────────────────────────────────────────────


async def _fetch_card_doc(card_id: str) -> dict | None:
    """
    Fetch a credit_cards document from MongoDB (async).
    Returns None on any failure.
    """
    try:
        from db.connection import get_db

        db = get_db()
        return await db["credit_cards"].find_one({"_id": card_id})
    except Exception as exc:
        logger.error("Failed to fetch card '%s' from DB: %s", card_id, exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Spend aggregation
# ─────────────────────────────────────────────────────────────────────────────


def _aggregate_spend_by_category(transactions: list[Transaction]) -> dict[str, float]:
    """Sum debit transaction amounts per category."""
    spend: dict[str, float] = defaultdict(float)
    for txn in transactions:
        if txn.get("transaction_type") == "debit":
            spend[txn["category"]] += txn["amount"]
    return dict(spend)


def _aggregate_spend_by_merchant(transactions: list[Transaction]) -> dict[str, float]:
    """Sum debit transaction amounts per lowercase merchant name."""
    spend: dict[str, float] = defaultdict(float)
    for txn in transactions:
        if txn.get("transaction_type") == "debit":
            spend[txn["merchant"].lower()] += txn["amount"]
    return dict(spend)


# ─────────────────────────────────────────────────────────────────────────────
# Auto-detection
# ─────────────────────────────────────────────────────────────────────────────


def _auto_detect_answers(
    utilization_questions: list[dict],
    transactions: list[Transaction],
    existing_answers: dict[str, bool],
) -> dict[str, bool]:
    """
    For each utilization_question, check if any transaction merchant contains
    any of the question's auto_detect_keywords.  If so, mark as True without
    asking the user.

    Returns an updated copy of existing_answers.
    """
    answers = dict(existing_answers)

    for q in utilization_questions:
        q_id = q.get("id", "")
        if q_id in answers:
            continue  # Already answered

        keywords = [kw.lower() for kw in q.get("auto_detect_keywords", [])]
        if not keywords:
            continue

        for txn in transactions:
            if txn.get("transaction_type") != "debit":
                continue
            merchant_lower = txn["merchant"].lower()
            if any(kw in merchant_lower for kw in keywords):
                answers[q_id] = True
                logger.debug(
                    "Auto-detected question '%s' answered True (merchant='%s')",
                    q_id,
                    txn["merchant"],
                )
                break

    return answers


# ─────────────────────────────────────────────────────────────────────────────
# Question building (offline — from card DB doc, no LLM needed)
# ─────────────────────────────────────────────────────────────────────────────


def _build_questions_from_card_doc(
    card_doc: dict,
    category_spend: dict[str, float],
    qa_answers: dict[str, bool],
) -> list[Question]:
    """
    Build the question list from the card's utilization_questions and benefits
    stored in MongoDB — no LLM call required.

    Steps:
      1. Walk utilization_questions from DB.
      2. Skip if already in qa_answers.
      3. Skip if category spend == 0 or benefit rate <= 1%.
      4. Enrich with detected_spend and potential_cashback.
      5. Add GENERAL questions (always 3, filtered to those not already answered).
      6. Sort by potential_cashback desc, cap at MAX_QUESTIONS_PER_CARD.
    """
    # Build a quick lookup: category → benefit rate
    benefit_rate: dict[str, float] = {}
    for b in card_doc.get("benefits", []):
        cat = b.get("category", "")
        rate = float(b.get("rate", 0))
        benefit_rate[cat] = max(benefit_rate.get(cat, 0), rate)

    questions: list[Question] = []

    for uq in card_doc.get("utilization_questions", []):
        q_id = uq.get("id", "")
        if not q_id:
            continue
        if q_id in qa_answers:
            continue  # Already answered (manually or auto-detected)

        category = uq.get("maps_to_category", "others")
        spend = category_spend.get(category, 0.0)
        rate = benefit_rate.get(category, 0.0)

        # Filter: spend > 0 AND rate > 1%
        if spend <= MIN_CATEGORY_SPEND or rate <= MIN_BENEFIT_RATE:
            continue

        potential = round(spend * rate, 2)
        pct = int(rate * 100)

        q: Question = {
            "id": q_id,
            "category": category,
            "text": uq.get("text", f"Do you use this card for {category}?"),
            "hint": uq.get("hint") or f"Earns {pct}% cashback — ₹{potential:.0f} potential this month",
            "detected_spend": round(spend, 2),
            "potential_cashback": potential,
            "is_general": False,
        }
        questions.append(q)

    # Add general questions (those not yet answered)
    for gq in GENERAL_QUESTIONS:
        if gq["id"] not in qa_answers:
            questions.append(Question(**gq))

    # Sort by potential_cashback descending (generals have 0 → appear last)
    questions.sort(key=lambda q: q["potential_cashback"], reverse=True)

    # Cap at MAX_QUESTIONS_PER_CARD
    return questions[:MAX_QUESTIONS_PER_CARD]


# ─────────────────────────────────────────────────────────────────────────────
# Optional LLM enrichment (question_gen_node uses this if GEMINI_API_KEY set)
# ─────────────────────────────────────────────────────────────────────────────


def _enrich_questions_with_llm(
    card_doc: dict,
    category_spend: dict[str, float],
    base_questions: list[Question],
) -> list[Question]:
    """
    Optionally call Gemini Flash to generate/enrich questions.
    Falls back to base_questions if GEMINI_API_KEY is missing or the call fails.
    The base_questions list is always used as the floor — LLM output supplements
    but never replaces auto-detected or general questions.
    """
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        logger.debug("No GEMINI_API_KEY — using rule-based questions only")
        return base_questions

    try:
        import json as _json

        from langchain_google_genai import ChatGoogleGenerativeAI

        # Build compact context for Gemini
        benefits_summary = [
            {"category": b["category"], "label": b.get("label", ""), "rate": b.get("rate", 0)}
            for b in card_doc.get("benefits", [])
            if float(b.get("rate", 0)) > MIN_BENEFIT_RATE
        ]
        cat_spend_filtered = {k: v for k, v in category_spend.items() if v > 0}

        import re as _re

        prompt = QUESTION_GEN_PROMPT.format(
            card_name=card_doc.get("name", ""),
            card_bank=card_doc.get("bank", ""),
            benefits_json=_json.dumps(benefits_summary),
            category_spend_json=_json.dumps(cat_spend_filtered),
        )

        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=api_key,
            temperature=0,
        )
        response = llm.invoke(prompt)
        raw = response.content.replace("```json", "").replace("```", "").strip()

        # Extract JSON array
        match = _re.search(r"\[.*\]", raw, _re.DOTALL)
        raw_list = _json.loads(match.group(0)) if match else []

        if not isinstance(raw_list, list):
            return base_questions

        llm_questions: list[Question] = []
        seen_ids: set[str] = {q["id"] for q in base_questions}

        for item in raw_list:
            if not isinstance(item, dict):
                continue
            q_id = str(item.get("id", "")).strip()
            if not q_id or q_id in seen_ids:
                continue
            seen_ids.add(q_id)

            try:
                q = Question(
                    id=q_id,
                    category=str(item.get("category", "general")),
                    text=str(item.get("text", "")),
                    hint=str(item.get("hint", "")),
                    detected_spend=float(item.get("detected_spend", 0)),
                    potential_cashback=float(item.get("potential_cashback", 0)),
                    is_general=bool(item.get("is_general", False)),
                )
                llm_questions.append(q)
            except Exception:
                continue

        # Merge: base first, then LLM additions
        merged = base_questions + llm_questions
        merged.sort(key=lambda q: q["potential_cashback"], reverse=True)
        return merged[:MAX_QUESTIONS_PER_CARD]

    except Exception as exc:
        logger.warning("LLM question enrichment failed (using rule-based): %s", exc)
        return base_questions


# ─────────────────────────────────────────────────────────────────────────────
# Node
# ─────────────────────────────────────────────────────────────────────────────


async def question_gen_node(state: AnalysisState) -> dict[str, Any]:
    """
    LangGraph node — generate / advance utilization quiz questions.

    Called both on first entry (builds full question list) and after each
    user answer (re-evaluates remaining questions).

    Returns a dict of state fields to update.
    """
    cards: list[CardState] = deepcopy(state["cards"])
    card_idx: int = state["current_card_idx"]
    card: CardState = cards[card_idx]

    card_id: str = card["card_id"]
    transactions: list[Transaction] = card.get("transactions") or []
    qa_answers: dict[str, bool] = dict(card.get("qa_answers") or {})

    # ── 1. Load card document from DB ────────────────────────────────
    card_doc = await _fetch_card_doc(card_id)
    if card_doc is None:
        logger.error("question_gen_node: card '%s' not found in DB", card_id)
        # Graceful degradation — skip to calculating with only general questions
        card_doc = {"_id": card_id, "name": card_id, "bank": "", "benefits": [], "utilization_questions": []}

    # ── 2. Auto-detect answers ────────────────────────────────────────
    utilization_questions = card_doc.get("utilization_questions", [])
    qa_answers = _auto_detect_answers(utilization_questions, transactions, qa_answers)

    # ── 3. Aggregate spend by category ───────────────────────────────
    category_spend = _aggregate_spend_by_category(transactions)

    # ── 4. Build question list (rule-based) ───────────────────────────
    base_questions = _build_questions_from_card_doc(card_doc, category_spend, qa_answers)

    # ── 5. Optionally enrich with LLM ────────────────────────────────
    all_questions = await asyncio.to_thread(
        _enrich_questions_with_llm, card_doc, category_spend, base_questions
    )

    # ── 6. Split into pending vs answered ────────────────────────────
    pending: list[Question] = []
    answered: list[Question] = []
    for q in all_questions:
        if q["id"] in qa_answers:
            answered.append(q)
        else:
            pending.append(q)

    # Include previously answered questions that may not be in all_questions
    existing_answered = card.get("answered_questions") or []
    existing_ids = {q["id"] for q in answered}
    for aq in existing_answered:
        if aq["id"] not in existing_ids:
            answered.append(aq)

    # Totals — count answered from qa_answers (authoritative), total from pending + all ever asked
    answered_count = len(qa_answers)
    total_q = len(pending) + answered_count

    # ── 7. Determine next action ──────────────────────────────────────
    if pending:
        next_question = pending[0]
        card["pending_questions"] = pending
        card["answered_questions"] = answered
        card["qa_answers"] = qa_answers
        card["status"] = "questioning"
        cards[card_idx] = card

        logger.info(
            "question_gen_node: card_idx=%d pending=%d answered=%d next='%s'",
            card_idx,
            len(pending),
            len(answered),
            next_question["id"],
        )

        return {
            "cards": cards,
            "status": "questioning",
            "ui_action": "show_question",
            "current_question": next_question,
            "total_questions_count": total_q,
            "answered_questions_count": answered_count,
            "error": None,
        }

    # ── 8. All answered → advance to calculating ──────────────────────
    card["pending_questions"] = []
    card["answered_questions"] = answered
    card["qa_answers"] = qa_answers
    card["status"] = "calculating"
    cards[card_idx] = card

    logger.info(
        "question_gen_node: card_idx=%d all %d questions answered → calculating",
        card_idx,
        len(answered),
    )

    return {
        "cards": cards,
        "status": "calculating",
        "ui_action": "show_loading",
        "current_question": None,
        "total_questions_count": total_q,
        "answered_questions_count": answered_count,
        "error": None,
    }
