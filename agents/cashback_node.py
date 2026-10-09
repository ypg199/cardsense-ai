"""
agents/cashback_node.py
─────────────────────────────────────────────────────────────────────────────
Node 4: cashback_calc_node

Responsibilities
────────────────
1. Load the current card's document from MongoDB (benefits).
2. For each debit transaction, find the matching benefit by category.
3. Apply cashback rate ONLY if qa_answers confirms the user used that category
   (answer == True) OR the question was auto-detected as answered.
4. Apply max_cashback_per_month cap per benefit if set.
5. Compute missed cashback for categories where user answered No / unanswered.
6. Calculate Utilization Score (Section 10 algorithm).
7. For multi-month uploads: compute per-month breakdown AND trend direction.
8. Write CashbackResult to state and advance status to "comparing".

Utilization Score Formula (Section 10)
───────────────────────────────────────
  theoretical_max = Σ (spend_in_category × best_possible_rate)
                    for every category where card offers > 1% cashback

  actual_earned   = Σ (spend_in_category × rate)
                    only for categories user confirmed YES

  utilization_score = round((actual_earned / theoretical_max) × 100)
                      capped at 100

Score Labels
────────────
  90-100  Excellent — You are maximizing this card
  70-89   Good — Minor optimizations possible
  50-69   Average — Several opportunities missed
  30-49   Below average — Consider using this card differently
  0-29    Poor — This card may not suit your spending pattern

State fields read
─────────────────
  cards[current_card_idx].transactions
  cards[current_card_idx].qa_answers
  card document from MongoDB (benefits)
  current_card_idx

State fields written
────────────────────
  cards[current_card_idx].cashback_result   – CashbackResult
  cards[current_card_idx].utilization_score – int 0-100
  cards[current_card_idx].status            – "comparing"
  status                                    – "comparing"
  ui_action                                 – "show_loading"
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import logging
from collections import defaultdict
from copy import deepcopy
from typing import Any

from agents.state import (
    AnalysisState, CardState, CashbackResult, MonthlyBreakdown, Transaction
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Score labels (Section 10)
# ─────────────────────────────────────────────────────────────────────────────

SCORE_LABELS = [
    (90, "Excellent — You are maximizing this card"),
    (70, "Good — Minor optimizations possible"),
    (50, "Average — Several opportunities missed"),
    (30, "Below average — Consider using this card differently"),
    (0,  "Poor — This card may not suit your spending pattern"),
]


def get_score_label(score: int) -> str:
    for threshold, label in SCORE_LABELS:
        if score >= threshold:
            return label
    return SCORE_LABELS[-1][1]


# ─────────────────────────────────────────────────────────────────────────────
# DB helper (reuses pattern from question_node)
# ─────────────────────────────────────────────────────────────────────────────

async def _fetch_card_doc(card_id: str) -> dict | None:
    """Fetch a credit_cards document from MongoDB (async)."""
    try:
        from db.connection import get_db
        db = get_db()
        return await db["credit_cards"].find_one({"_id": card_id})
    except Exception as exc:
        logger.error("Failed to fetch card '%s' from DB: %s", card_id, exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Benefit index builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_benefit_index(card_doc: dict) -> dict[str, dict]:
    """
    Build a dict keyed by category → best benefit for that category.
    If multiple benefits map to the same category, keep the highest rate.
    """
    index: dict[str, dict] = {}
    for b in card_doc.get("benefits", []):
        cat = b.get("category", "")
        if not cat:
            continue
        existing = index.get(cat)
        if existing is None or float(b.get("rate", 0)) > float(existing.get("rate", 0)):
            index[cat] = b
    return index


# ─────────────────────────────────────────────────────────────────────────────
# Per-transaction cashback calculation
# ─────────────────────────────────────────────────────────────────────────────

def _calc_transaction_cashback(
    txn: Transaction,
    benefit: dict,
    monthly_earned_caps: dict[str, float],  # { "YYYY-MM:category": earned_so_far }
) -> float:
    """
    Calculate cashback for a single transaction, respecting monthly caps.
    Returns the INR cashback earned (0 if capped or not applicable).
    """
    amount = txn["amount"]
    rate = float(benefit.get("rate", 0))
    raw_cashback = round(amount * rate, 2)

    cap = benefit.get("max_cashback_per_month")
    if cap is not None:
        cap = float(cap)
        cap_key = f"{txn['month']}:{benefit['category']}"
        already_earned = monthly_earned_caps.get(cap_key, 0.0)
        remaining_cap = max(0.0, cap - already_earned)
        actual_cashback = min(raw_cashback, remaining_cap)
        monthly_earned_caps[cap_key] = already_earned + actual_cashback
        return actual_cashback

    return raw_cashback


# ─────────────────────────────────────────────────────────────────────────────
# Core calculation
# ─────────────────────────────────────────────────────────────────────────────

def calculate_cashback(
    transactions: list[Transaction],
    qa_answers: dict[str, bool],
    card_doc: dict,
) -> CashbackResult:
    """
    Pure function — no I/O.  Computes the full CashbackResult for one card.

    Parameters
    ----------
    transactions : list of Transaction dicts (may span multiple months)
    qa_answers   : { question_id: bool } — True = user confirmed usage
    card_doc     : MongoDB credit_cards document (has benefits + utilization_questions)

    Returns
    -------
    CashbackResult TypedDict
    """
    benefit_index = _build_benefit_index(card_doc)

    # Build category → question_id mapping so we can check qa_answers
    # (utilization_questions.maps_to_category → question id)
    category_to_qids: dict[str, list[str]] = defaultdict(list)
    for uq in card_doc.get("utilization_questions", []):
        cat = uq.get("maps_to_category", "")
        qid = uq.get("id", "")
        if cat and qid:
            category_to_qids[cat].append(qid)

    def _user_confirmed(category: str) -> bool:
        """
        Return True if the user confirmed (or auto-confirmed) usage of
        this category.  Logic:
        - If NO question maps to this category → assume True (no restriction).
        - If ANY question for this category is answered True → True.
        - If all questions answered False → False.
        - If no answer recorded for any question → False (unanswered = missed).
        """
        qids = category_to_qids.get(category, [])
        if not qids:
            return True  # No gating question — count full cashback
        return any(qa_answers.get(qid) is True for qid in qids)

    # ── Group transactions by month ───────────────────────────────────
    months_seen: set[str] = set()
    txns_by_month: dict[str, list[Transaction]] = defaultdict(list)
    for txn in transactions:
        if txn.get("transaction_type") == "debit":
            month = txn.get("month", "2024-01")
            txns_by_month[month].append(txn)
            months_seen.add(month)

    sorted_months = sorted(months_seen)

    # ── Accumulators ─────────────────────────────────────────────────
    total_earned: dict[str, float] = defaultdict(float)
    total_missed: dict[str, float] = defaultdict(float)
    monthly_breakdowns: list[MonthlyBreakdown] = []

    # Tracks running cap totals: "YYYY-MM:category" → INR earned so far
    monthly_earned_caps: dict[str, float] = {}

    # For utilization score: theoretical max per category (across all months)
    theoretical_by_category: dict[str, float] = defaultdict(float)
    actual_by_category: dict[str, float] = defaultdict(float)

    for month in sorted_months:
        month_earned: dict[str, float] = defaultdict(float)
        month_missed: dict[str, float] = defaultdict(float)

        for txn in txns_by_month[month]:
            category = txn.get("category", "others")
            benefit = benefit_index.get(category) or benefit_index.get("others")

            if benefit is None:
                continue

            rate = float(benefit.get("rate", 0))
            amount = txn["amount"]

            # Theoretical max (rate > 1% only — spec Section 10)
            if rate > 0.01:
                theoretical_by_category[category] += amount * rate

            if _user_confirmed(category):
                # Earned
                cashback = _calc_transaction_cashback(txn, benefit, monthly_earned_caps)
                month_earned[category] += cashback
                total_earned[category] += cashback
                if rate > 0.01:
                    actual_by_category[category] += cashback
            else:
                # Missed — what they could have earned
                if rate > 0.01:
                    raw = round(amount * rate, 2)
                    month_missed[category] += raw
                    total_missed[category] += raw

        month_earned_total = round(sum(month_earned.values()), 2)
        month_missed_total = round(sum(month_missed.values()), 2)
        month_max = month_earned_total + month_missed_total
        month_score = (
            round((month_earned_total / month_max) * 100)
            if month_max > 0 else 0
        )

        monthly_breakdowns.append(MonthlyBreakdown(
            month=month,
            earned=month_earned_total,
            missed=month_missed_total,
            score=month_score,
        ))

    # ── Utilization Score (Section 10 formula) ────────────────────────
    theoretical_max = sum(theoretical_by_category.values())
    actual_earned_total = sum(actual_by_category.values())

    if theoretical_max > 0:
        raw_score = (actual_earned_total / theoretical_max) * 100
        utilization_score = min(100, round(raw_score))
    else:
        utilization_score = 0

    # ── Trend calculation ─────────────────────────────────────────────
    trend = _compute_trend([mb["score"] for mb in monthly_breakdowns])

    # ── Round final totals ────────────────────────────────────────────
    earned_breakdown = {k: round(v, 2) for k, v in total_earned.items() if v > 0}
    missed_breakdown = {k: round(v, 2) for k, v in total_missed.items() if v > 0}

    return CashbackResult(
        earned_breakdown=earned_breakdown,
        missed_breakdown=missed_breakdown,
        utilization_score=utilization_score,
        monthly_breakdown=monthly_breakdowns,
        trend=trend,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Trend helper
# ─────────────────────────────────────────────────────────────────────────────

def _compute_trend(scores: list[int]) -> str:
    """
    Compute trend direction from a list of monthly utilization scores.

    Returns: "improving" | "declining" | "flat" | "single_month"
    """
    if len(scores) <= 1:
        return "single_month"

    # Compare first half average to second half average
    mid = len(scores) // 2
    first_avg = sum(scores[:mid]) / mid
    second_avg = sum(scores[mid:]) / (len(scores) - mid)

    diff = second_avg - first_avg
    if diff > 5:
        return "improving"
    elif diff < -5:
        return "declining"
    else:
        return "flat"


# ─────────────────────────────────────────────────────────────────────────────
# Node
# ─────────────────────────────────────────────────────────────────────────────

async def cashback_calc_node(state: AnalysisState) -> dict[str, Any]:
    """
    LangGraph node — calculate cashback and utilization score for the current card.
    Returns a dict of state fields to update.
    """
    cards: list[CardState] = deepcopy(state["cards"])
    card_idx: int = state["current_card_idx"]
    card: CardState = cards[card_idx]

    card_id: str = card["card_id"]
    transactions: list[Transaction] = card.get("transactions") or []
    qa_answers: dict[str, bool] = card.get("qa_answers") or {}

    # ── Load card document ────────────────────────────────────────────
    card_doc = await _fetch_card_doc(card_id)
    if card_doc is None:
        logger.error("cashback_calc_node: card '%s' not found in DB — using empty doc", card_id)
        card_doc = {"_id": card_id, "benefits": [], "utilization_questions": []}

    # ── Calculate ─────────────────────────────────────────────────────
    try:
        result = calculate_cashback(transactions, qa_answers, card_doc)
    except Exception as exc:
        logger.error("cashback_calc_node calculation error for card '%s': %s", card_id, exc)
        result = CashbackResult(
            earned_breakdown={},
            missed_breakdown={},
            utilization_score=0,
            monthly_breakdown=[],
            trend="single_month",
        )

    card["cashback_result"] = result
    card["utilization_score"] = result["utilization_score"]
    card["status"] = "comparing"
    cards[card_idx] = card

    logger.info(
        "cashback_calc_node: card_idx=%d score=%d earned=₹%.2f missed=₹%.2f trend=%s",
        card_idx,
        result["utilization_score"],
        sum(result["earned_breakdown"].values()),
        sum(result["missed_breakdown"].values()),
        result["trend"],
    )

    return {
        "cards": cards,
        "status": "comparing",
        "ui_action": "show_loading",
        "error": None,
    }
