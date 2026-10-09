"""
agents/compare_node.py
─────────────────────────────────────────────────────────────────────────────
Node 5: compare_node

Responsibilities
────────────────
1. Build a spend-profile text from the user's top 3 spend categories.
2. Embed with text-embedding-004 (768-dim) and run MongoDB Atlas $vectorSearch
   on credit_cards collection to retrieve top 10 candidates.
3. Rule-filter candidates: remove current card(s), cards with incompatible
   card_type for the user's spend pattern.
4. Send filtered candidates + cashback summary to gemini-2.5-flash for ranking.
5. Write ComparisonResult to state and advance status to "done".

Section 9 — Multi-card logic
─────────────────────────────
  Step 1: For each spend category, find which of the user's own cards gives
          the best rate.
  Step 2: Calculate "optimal portfolio cashback" = routing each category to
          best card.
  Step 3: Calculate "actual cashback" = what user actually earned.
  Step 4: Gap = optimal - actual (improvement from better routing).
  Step 5: Vector search for external cards that beat even optimal routing.
  Step 6: Gemini Pro: rank + explain top 3 external alternatives.

Section 14 — Known pitfalls handled
─────────────────────────────────────
  - Atlas Vector Search not set up → fall back to category filter query.
  - Gemini JSON wrapped in ``` fences → strip before json.loads().
  - text-embedding-004 returns 768 dimensions.

State fields read
─────────────────
  cards[*].card_id, cards[*].cashback_result, cards[*].transactions
  current_card_idx

State fields written
────────────────────
  comparison_result   – ComparisonResult
  status              – "done"
  ui_action           – "show_results"
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from collections import defaultdict
from copy import deepcopy
from typing import Any

from dotenv import load_dotenv
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from agents.state import AnalysisState, CardRecommendation, CardState, ComparisonResult

load_dotenv()
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

VECTOR_SEARCH_INDEX = "credit_cards_embedding_index"
VECTOR_SEARCH_CANDIDATES = 10
EMBEDDING_DIMENSIONS = 768

# Categories that indicate a "travel" user (used for card_type filter)
TRAVEL_CATEGORIES = {"travel_flights", "travel_hotels"}
FUEL_CATEGORIES = {"fuel"}

# ── Exact prompt from Section 11 ─────────────────────────────────────────────
COMPARISON_PROMPT = """\
You are a senior credit card advisor for India. Be specific and data-driven.

User's card(s): {current_cards_summary}

Monthly spend analysis: {cashback_summary_json}

Top 3 spending categories: {top_categories}

Total monthly spend: ₹{total_spend}

Alternative cards from database:
{alt_cards_json}

Return ONLY valid JSON:
{{
  "verdict": "Good fit|Could do better|Switch recommended",
  "verdict_reason": "One specific sentence with numbers",
  "card_score": 72,
  "recommendations": [
    {{
      "card_id": "slug",
      "card_name": "Name",
      "bank": "Bank",
      "estimated_monthly_cashback": 1200,
      "estimated_annual_cashback": 14400,
      "improvement_over_current_monthly": 350,
      "why_better": "2 sentences with specific % and ₹ amounts",
      "best_categories": ["food","grocery"],
      "caveat": "One caveat string or null"
    }}
  ],
  "routing_advice": [
    "Use Axis Airtel for Zomato (25% vs 1% on HDFC)"
  ],
  "tips": ["Tip 1", "Tip 2", "Tip 3"]
}}"""


# ─────────────────────────────────────────────────────────────────────────────
# DB helpers
# ─────────────────────────────────────────────────────────────────────────────


async def _run_async(coro):
    """Await a coroutine directly (we are always in async context)."""
    return await coro


async def _fetch_cards_by_categories_async(top_categories: list[str]) -> list[dict]:
    """
    Category-filter fallback: find cards that have benefits in any of the
    top_categories. Used when Atlas Vector Search is not yet configured.
    """
    from db.connection import get_db

    db = get_db()
    cursor = (
        db["credit_cards"]
        .find(
            {"benefits.category": {"$in": top_categories}},
            {"embedding": 0},  # Exclude large embedding vectors from results
        )
        .limit(VECTOR_SEARCH_CANDIDATES)
    )
    return await cursor.to_list(length=VECTOR_SEARCH_CANDIDATES)


async def _vector_search_async(embedding: list[float], top_categories: list[str]) -> list[dict]:
    """
    Run Atlas $vectorSearch. Falls back to category filter if the index
    doesn't exist or the search fails (Section 14 pitfall).
    """
    from db.connection import get_db

    db = get_db()

    try:
        pipeline = [
            {
                "$vectorSearch": {
                    "index": VECTOR_SEARCH_INDEX,
                    "path": "embedding",
                    "queryVector": embedding,
                    "numCandidates": VECTOR_SEARCH_CANDIDATES * 10,
                    "limit": VECTOR_SEARCH_CANDIDATES,
                }
            },
            {
                "$project": {
                    "embedding": 0,  # Don't return the 768-float array
                    "score": {"$meta": "vectorSearchScore"},
                }
            },
        ]
        results = await db["credit_cards"].aggregate(pipeline).to_list(length=VECTOR_SEARCH_CANDIDATES)
        if results:
            logger.info("Vector search returned %d candidates", len(results))
            return results
        # Empty results — fall back
        logger.warning("Vector search returned 0 results — falling back to category filter")
    except Exception as exc:
        logger.warning("Atlas Vector Search failed (%s) — falling back to category filter", exc)

    return await _fetch_cards_by_categories_async(top_categories)


def _get_embedding(text: str) -> list[float]:
    """
    Embed text with text-embedding-004 (768-dim).
    Returns zero vector on failure (so vector search gracefully degrades).
    """
    try:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        embedder = GoogleGenerativeAIEmbeddings(
            model="models/text-embedding-004",
            google_api_key=os.getenv("GEMINI_API_KEY", ""),
        )
        vec = embedder.embed_query(text)
        if len(vec) != EMBEDDING_DIMENSIONS:
            logger.warning(
                "Embedding dimension mismatch: got %d, expected %d", len(vec), EMBEDDING_DIMENSIONS
            )
        return vec
    except Exception as exc:
        logger.warning("Embedding failed: %s — using zero vector (category fallback)", exc)
        return [0.0] * EMBEDDING_DIMENSIONS


# ─────────────────────────────────────────────────────────────────────────────
# Spend analysis helpers
# ─────────────────────────────────────────────────────────────────────────────


def _aggregate_cross_card_spend(cards: list[CardState]) -> dict[str, float]:
    """Aggregate total spend by category across ALL cards."""
    spend: dict[str, float] = defaultdict(float)
    for card in cards:
        for txn in card.get("transactions") or []:
            if txn.get("transaction_type") == "debit":
                spend[txn["category"]] += txn["amount"]
    return dict(spend)


def _top_categories(spend: dict[str, float], n: int = 3) -> list[str]:
    """Return the top-n categories by spend, excluding 'others'."""
    filtered = {k: v for k, v in spend.items() if k != "others" and v > 0}
    return sorted(filtered, key=lambda k: filtered[k], reverse=True)[:n]


def _build_spend_profile_text(cards: list[CardState], top_cats: list[str]) -> str:
    """Build the embedding source text from user's spend profile."""
    spend = _aggregate_cross_card_spend(cards)
    parts = [f"{cat}: ₹{spend.get(cat, 0):.0f}" for cat in top_cats]
    return f"Indian credit card user. Top spending categories: {', '.join(parts)}"


def _total_monthly_spend(cards: list[CardState]) -> float:
    return sum(c.get("total_spend", 0.0) for c in cards)


# ─────────────────────────────────────────────────────────────────────────────
# Multi-card routing analysis (Section 9)
# ─────────────────────────────────────────────────────────────────────────────


def _compute_routing_advice(cards: list[CardState]) -> list[str]:
    """
    Section 9 Step 1-4: For each spend category, identify which of the
    user's own cards gives the best rate and generate routing advice.
    """
    if len(cards) <= 1:
        return []

    # Build per-card benefit rate index
    card_benefit_rates: dict[str, dict[str, float]] = {}
    for card in cards:
        card_id = card["card_id"]
        card_name = card.get("card_name", card_id)
        # Load from cashback_result if available, or skip
        cr = card.get("cashback_result")
        if not cr:
            continue
        # We'll use the earned + missed breakdown to infer rates
        card_benefit_rates[card_id] = {"_name": card_name}

    # Aggregate spend by category
    spend = _aggregate_cross_card_spend(cards)
    advice: list[str] = []

    # Compare across cards for each high-spend category
    # This is a best-effort analysis using available cashback data
    for cat, cat_spend in sorted(spend.items(), key=lambda x: x[1], reverse=True):
        if cat == "others" or cat_spend < 500:
            continue
        best_card_name = None
        best_rate_pct = 0
        worst_rate_pct = 100

        for card in cards:
            cr = card.get("cashback_result")
            if not cr:
                continue
            earned = cr.get("earned_breakdown", {}).get(cat, 0)
            missed = cr.get("missed_breakdown", {}).get(cat, 0)
            total_possible = earned + missed
            if total_possible > 0 and cat_spend > 0:
                effective_rate = (total_possible / cat_spend) * 100
                if effective_rate > best_rate_pct:
                    best_rate_pct = effective_rate
                    best_card_name = card.get("card_name", card["card_id"])
                worst_rate_pct = min(worst_rate_pct, effective_rate)

        if best_card_name and best_rate_pct > worst_rate_pct and (best_rate_pct - worst_rate_pct) > 1:
            cat_label = cat.replace("_", " ").title()
            advice.append(
                f"Use {best_card_name} for {cat_label} "
                f"({best_rate_pct:.0f}% vs {worst_rate_pct:.0f}% on other cards)"
            )
        if len(advice) >= 5:
            break

    return advice


def _build_cashback_summary(cards: list[CardState]) -> dict:
    """Build a compact cashback summary for the Gemini Pro prompt."""
    summary: dict[str, Any] = {
        "cards": [],
        "total_earned": 0.0,
        "total_missed": 0.0,
    }
    for card in cards:
        cr = card.get("cashback_result")
        if not cr:
            continue
        earned = sum(cr.get("earned_breakdown", {}).values())
        missed = sum(cr.get("missed_breakdown", {}).values())
        summary["cards"].append(
            {
                "card_id": card["card_id"],
                "card_name": card.get("card_name", ""),
                "utilization_score": cr.get("utilization_score", 0),
                "earned_inr": round(earned, 2),
                "missed_inr": round(missed, 2),
                "earned_by_category": cr.get("earned_breakdown", {}),
            }
        )
        summary["total_earned"] += earned
        summary["total_missed"] += missed

    summary["total_earned"] = round(summary["total_earned"], 2)
    summary["total_missed"] = round(summary["total_missed"], 2)
    return summary


# ─────────────────────────────────────────────────────────────────────────────
# Rule filter (Section 5 — Step 2)
# ─────────────────────────────────────────────────────────────────────────────


def _rule_filter_candidates(
    candidates: list[dict],
    current_card_ids: set[str],
    spend: dict[str, float],
) -> list[dict]:
    """
    Remove candidates that are:
    1. Already one of the user's current cards.
    2. Completely wrong card_type for the user's spend pattern.
       (e.g. pure travel card for a user with 0 travel spend)
    """
    travel_spend = sum(spend.get(c, 0) for c in TRAVEL_CATEGORIES)
    fuel_spend = spend.get("fuel", 0)
    total_spend = sum(spend.values()) or 1

    filtered: list[dict] = []
    for card in candidates:
        cid = card.get("_id", "")

        # Skip current cards
        if cid in current_card_ids:
            continue

        card_type = card.get("card_type", "cashback")

        # Skip pure travel cards if user has < 5% travel spend
        if card_type == "travel" and (travel_spend / total_spend) < 0.05:
            continue

        # Skip pure fuel cards if user has < 3% fuel spend
        if card_type == "fuel" and (fuel_spend / total_spend) < 0.03:
            continue

        filtered.append(card)

    return filtered


# ─────────────────────────────────────────────────────────────────────────────
# Gemini Pro ranking (Section 5 — Step 3)
# ─────────────────────────────────────────────────────────────────────────────


def _clean_json(raw: str) -> str:
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    return match.group(0) if match else cleaned


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
def _call_gemini_pro(prompt: str) -> str:
    from langchain_google_genai import ChatGoogleGenerativeAI

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=os.getenv("GEMINI_API_KEY", ""),
        temperature=0,
    )
    return llm.invoke(prompt).content


def _rank_with_gemini(
    cards_summary: dict,
    alt_cards: list[dict],
    top_cats: list[str],
    total_spend: float,
    routing_advice: list[str],
) -> ComparisonResult:
    """
    Call Gemini 2.5-flash to rank alternatives and produce the full ComparisonResult.
    Falls back to a rule-based result if Gemini fails or no API key.
    """
    api_key = os.getenv("GEMINI_API_KEY", "")

    if not api_key or not alt_cards:
        return _rule_based_result(cards_summary, alt_cards, top_cats, total_spend, routing_advice)

    # Compact alt_cards for the prompt (drop heavy fields)
    alt_cards_compact = [
        {
            "card_id": c.get("_id", ""),
            "name": c.get("name", ""),
            "bank": c.get("bank", ""),
            "card_type": c.get("card_type", ""),
            "annual_fee": c.get("annual_fee", 0),
            "benefits": [
                {"category": b.get("category"), "rate": b.get("rate"), "label": b.get("label")}
                for b in c.get("benefits", [])[:6]
            ],
            "best_for_tags": c.get("best_for_tags", []),
        }
        for c in alt_cards[:6]  # Limit to 6 to stay within token budget
    ]

    current_cards_summary = (
        "; ".join(
            f"{c['card_name']} (score {c['utilization_score']}/100, "
            f"earned ₹{c['earned_inr']}, missed ₹{c['missed_inr']})"
            for c in cards_summary.get("cards", [])
        )
        or "No card data"
    )

    prompt = COMPARISON_PROMPT.format(
        current_cards_summary=current_cards_summary,
        cashback_summary_json=json.dumps(cards_summary, indent=2),
        top_categories=", ".join(top_cats),
        total_spend=f"{total_spend:,.0f}",
        alt_cards_json=json.dumps(alt_cards_compact, indent=2),
    )

    try:
        raw = _call_gemini_pro(prompt)
        cleaned = _clean_json(raw)
        data = json.loads(cleaned)
    except Exception as exc:
        logger.error("Gemini Pro ranking failed: %s — using rule-based fallback", exc)
        return _rule_based_result(cards_summary, alt_cards, top_cats, total_spend, routing_advice)

    # Parse and validate recommendations
    recommendations: list[CardRecommendation] = []
    for item in data.get("recommendations", [])[:3]:
        try:
            recommendations.append(
                CardRecommendation(
                    card_id=str(item.get("card_id", "")),
                    card_name=str(item.get("card_name", "")),
                    bank=str(item.get("bank", "")),
                    estimated_monthly_cashback=float(item.get("estimated_monthly_cashback", 0)),
                    estimated_annual_cashback=float(item.get("estimated_annual_cashback", 0)),
                    improvement_over_current_monthly=float(item.get("improvement_over_current_monthly", 0)),
                    why_better=str(item.get("why_better", "")),
                    best_categories=list(item.get("best_categories", [])),
                    caveat=item.get("caveat") or None,
                )
            )
        except Exception as e:
            logger.warning("Skipping malformed recommendation: %s", e)

    # Merge routing_advice: prefer Gemini's, supplement with ours
    gemini_routing = list(data.get("routing_advice", []))
    merged_routing = gemini_routing or routing_advice

    return ComparisonResult(
        verdict=str(data.get("verdict", "Could do better")),
        verdict_reason=str(data.get("verdict_reason", "")),
        card_score=min(100, max(0, int(data.get("card_score", 50)))),
        recommendations=recommendations,
        routing_advice=merged_routing[:5],
        tips=list(data.get("tips", []))[:5],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Rule-based fallback result (no Gemini / no candidates)
# ─────────────────────────────────────────────────────────────────────────────


def _rule_based_result(
    cards_summary: dict,
    alt_cards: list[dict],
    top_cats: list[str],
    total_spend: float,
    routing_advice: list[str],
) -> ComparisonResult:
    """
    Produce a basic ComparisonResult without Gemini.
    Used when API key is missing or all Gemini retries exhausted.
    """
    avg_score = 0
    if cards_summary.get("cards"):
        avg_score = round(
            sum(c["utilization_score"] for c in cards_summary["cards"]) / len(cards_summary["cards"])
        )

    if avg_score >= 70:
        verdict = "Good fit"
        verdict_reason = (
            f"You are utilizing {avg_score}% of your card's potential "
            f"with ₹{cards_summary.get('total_earned', 0):.0f} earned monthly."
        )
    elif avg_score >= 40:
        verdict = "Could do better"
        verdict_reason = (
            f"You are only capturing {avg_score}% of your card's potential. "
            f"₹{cards_summary.get('total_missed', 0):.0f} in cashback is being missed monthly."
        )
    else:
        verdict = "Switch recommended"
        verdict_reason = (
            f"Your card utilization is only {avg_score}%. "
            f"₹{cards_summary.get('total_missed', 0):.0f} in monthly cashback is being missed."
        )

    # Build basic recommendations from alt_cards
    recommendations: list[CardRecommendation] = []
    for c in alt_cards[:3]:
        benefit_rates = {b["category"]: b["rate"] for b in c.get("benefits", [])}
        est_monthly = sum(
            total_spend * 0.2 * benefit_rates.get(cat, 0)  # rough 20% of spend in each top cat
            for cat in top_cats
        )
        recommendations.append(
            CardRecommendation(
                card_id=c.get("_id", ""),
                card_name=c.get("name", ""),
                bank=c.get("bank", ""),
                estimated_monthly_cashback=round(est_monthly, 2),
                estimated_annual_cashback=round(est_monthly * 12, 2),
                improvement_over_current_monthly=max(
                    0.0, round(est_monthly - cards_summary.get("total_earned", 0), 2)
                ),
                why_better=f"Offers better rates for {', '.join(top_cats[:2])} spending.",
                best_categories=top_cats[:2],
                caveat=f"Annual fee: ₹{c.get('annual_fee', 0)}" if c.get("annual_fee") else None,
            )
        )

    tips = (
        [
            f"Focus your {top_cats[0].replace('_', ' ')} spending on the card with the highest rate.",
            "Set up auto-pay for utility bills on your highest utility cashback card.",
            "Check your card's offer portal before large purchases for extra cashback.",
        ]
        if top_cats
        else [
            "Review your card's benefit categories and align your spending.",
            "Use your card for recurring bills to earn passive cashback.",
        ]
    )

    return ComparisonResult(
        verdict=verdict,
        verdict_reason=verdict_reason,
        card_score=avg_score,
        recommendations=recommendations,
        routing_advice=routing_advice[:5],
        tips=tips[:5],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Node
# ─────────────────────────────────────────────────────────────────────────────


async def compare_node(state: AnalysisState) -> dict[str, Any]:
    """
    LangGraph node — compare user's cards against the database and generate
    recommendations.  Uses gemini-2.5-flash for the final ranking step.

    Returns a dict of state fields to update.
    """
    cards: list[CardState] = deepcopy(state["cards"])
    current_card_ids = {c["card_id"] for c in cards}

    # ── 1. Aggregate spend across all cards ──────────────────────────
    spend = _aggregate_cross_card_spend(cards)
    top_cats = _top_categories(spend, n=3)
    total_spend = _total_monthly_spend(cards)

    logger.info(
        "compare_node: %d card(s), total_spend=₹%.0f, top_cats=%s",
        len(cards),
        total_spend,
        top_cats,
    )

    # ── 2. Build spend-profile embedding text ─────────────────────────
    profile_text = _build_spend_profile_text(cards, top_cats)

    # ── 3. Embed + vector search (with category fallback) ────────────
    embedding = await asyncio.to_thread(_get_embedding, profile_text)
    candidates = await _run_async(_vector_search_async(embedding, top_cats))

    logger.info("Vector search / category fallback returned %d candidates", len(candidates))

    # ── 4. Rule filter ────────────────────────────────────────────────
    filtered = _rule_filter_candidates(candidates, current_card_ids, spend)
    logger.info("After rule filter: %d candidates", len(filtered))

    # ── 5. Multi-card routing advice (Section 9) ──────────────────────
    routing_advice = _compute_routing_advice(cards)

    # ── 6. Build cashback summary for Gemini ─────────────────────────
    cashback_summary = _build_cashback_summary(cards)

    # ── 7. Gemini Pro ranking ─────────────────────────────────────────
    comparison_result = await asyncio.to_thread(
        _rank_with_gemini, cashback_summary, filtered, top_cats, total_spend, routing_advice
    )

    logger.info(
        "compare_node complete — verdict='%s' score=%d recs=%d",
        comparison_result["verdict"],
        comparison_result["card_score"],
        len(comparison_result["recommendations"]),
    )

    return {
        "cards": cards,
        "comparison_result": comparison_result,
        "status": "done",
        "ui_action": "show_results",
        "error": None,
    }
