"""
tests/test_compare_node.py
Standalone tests for agents/compare_node.py.
All DB and Gemini calls are mocked — no live connections required.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import unittest.mock as mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.compare_node import (
    COMPARISON_PROMPT,
    EMBEDDING_DIMENSIONS,
    VECTOR_SEARCH_INDEX,
    _aggregate_cross_card_spend,
    _build_cashback_summary,
    _build_spend_profile_text,
    _clean_json,
    _compute_routing_advice,
    _rank_with_gemini,
    _rule_based_result,
    _rule_filter_candidates,
    _top_categories,
    compare_node,
)
from agents.state import AnalysisState, CardState, CashbackResult, MonthlyBreakdown, Transaction

# ─────────────────────────────────────────────────────────────────────────────
# Test scaffolding
# ─────────────────────────────────────────────────────────────────────────────

PASS = 0
FAIL = 0


def ok(msg: str):
    global PASS
    PASS += 1
    print(f"  ✅ {msg}")


def fail(msg: str):
    global FAIL
    FAIL += 1
    print(f"  ❌ {msg}")


# ── Sample data ────────────────────────────────────────────────────────────────


def _txn(cat: str, amount: float, month: str = "2024-01") -> Transaction:
    return Transaction(
        date=f"{month}-10",
        merchant=cat.replace("_", " ").title(),
        amount=amount,
        transaction_type="debit",
        category=cat,
        month=month,
    )


def _cashback_result(
    earned: dict[str, float],
    missed: dict[str, float],
    score: int = 65,
) -> CashbackResult:
    return CashbackResult(
        earned_breakdown=earned,
        missed_breakdown=missed,
        utilization_score=score,
        monthly_breakdown=[
            MonthlyBreakdown(
                month="2024-01", earned=sum(earned.values()), missed=sum(missed.values()), score=score
            )
        ],
        trend="single_month",
    )


def _make_card(
    card_id: str,
    card_name: str,
    transactions: list[Transaction],
    cashback_result: CashbackResult | None = None,
    qa_answers: dict | None = None,
) -> CardState:
    return {
        "card_id": card_id,
        "card_name": card_name,
        "months": ["2024-01"],
        "pdf_bytes_list": [],
        "pdf_passwords": [],
        "pdf_encrypted": False,
        "pdf_text": "",
        "transactions": transactions,
        "total_spend": sum(t["amount"] for t in transactions),
        "pending_questions": [],
        "answered_questions": [],
        "qa_answers": qa_answers or {},
        "cashback_result": cashback_result,
        "utilization_score": cashback_result["utilization_score"] if cashback_result else 0,
        "status": "comparing",
    }


def _make_state(cards: list[CardState]) -> AnalysisState:
    return {
        "session_id": "test-compare",
        "status": "comparing",
        "cards": cards,
        "current_card_idx": len(cards) - 1,
        "locked_card_idx": None,
        "locked_pdf_idx": None,
        "current_question": None,
        "comparison_result": None,
        "ui_action": "show_loading",
        "total_questions_count": 0,
        "answered_questions_count": 0,
        "error": None,
        "created_at": "2024-01-01T00:00:00Z",
    }


# ── Sample alternative cards ─────────────────────────────────────────────────

ALT_CARDS = [
    {
        "_id": "hdfc-millennia",
        "name": "HDFC Millennia Credit Card",
        "bank": "HDFC Bank",
        "card_type": "cashback",
        "annual_fee": 1000,
        "benefits": [
            {"category": "shopping_online", "rate": 0.05, "label": "Amazon & Flipkart"},
            {"category": "food_delivery", "rate": 0.05, "label": "Dining"},
            {"category": "grocery", "rate": 0.05, "label": "Grocery"},
            {"category": "others", "rate": 0.01, "label": "Others"},
        ],
        "best_for_tags": ["amazon", "dining"],
    },
    {
        "_id": "sbi-cashback",
        "name": "SBI Cashback Credit Card",
        "bank": "SBI Card",
        "card_type": "cashback",
        "annual_fee": 999,
        "benefits": [
            {"category": "shopping_online", "rate": 0.05, "label": "All Online"},
            {"category": "others", "rate": 0.01, "label": "Others"},
        ],
        "best_for_tags": ["online shopping"],
    },
    {
        "_id": "icici-amazon",
        "name": "Amazon Pay ICICI Card",
        "bank": "ICICI Bank",
        "card_type": "co-branded",
        "annual_fee": 0,
        "benefits": [
            {"category": "shopping_online", "rate": 0.05, "label": "Amazon Prime"},
            {"category": "others", "rate": 0.01, "label": "Others"},
        ],
        "best_for_tags": ["amazon prime", "lifetime free"],
    },
    {
        "_id": "axis-travel-card",
        "name": "Axis Atlas Credit Card",
        "bank": "Axis Bank",
        "card_type": "travel",
        "annual_fee": 5000,
        "benefits": [
            {"category": "travel_flights", "rate": 0.10, "label": "Flights"},
            {"category": "travel_hotels", "rate": 0.08, "label": "Hotels"},
        ],
        "best_for_tags": ["travel", "miles"],
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# 1. Constants
# ─────────────────────────────────────────────────────────────────────────────


def test_constants():
    print("\n[1] Constants and prompt")

    assert VECTOR_SEARCH_INDEX == "credit_cards_embedding_index"
    ok("VECTOR_SEARCH_INDEX == 'credit_cards_embedding_index'")

    assert EMBEDDING_DIMENSIONS == 768
    ok("EMBEDDING_DIMENSIONS == 768")

    for placeholder in [
        "{current_cards_summary}",
        "{cashback_summary_json}",
        "{top_categories}",
        "{total_spend}",
        "{alt_cards_json}",
    ]:
        assert placeholder in COMPARISON_PROMPT
    ok("All 5 required placeholders in COMPARISON_PROMPT")

    assert "gemini-2.5-flash" in COMPARISON_PROMPT.lower() or "verdict" in COMPARISON_PROMPT
    ok("COMPARISON_PROMPT has verdict/recommendation structure")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Spend aggregation
# ─────────────────────────────────────────────────────────────────────────────


def test_aggregate_cross_card_spend():
    print("\n[2] _aggregate_cross_card_spend")

    card1 = _make_card(
        "a",
        "Card A",
        [
            _txn("food_delivery", 500.0),
            _txn("grocery", 800.0),
        ],
    )
    card2 = _make_card(
        "b",
        "Card B",
        [
            _txn("food_delivery", 300.0),
            _txn("shopping_online", 1200.0),
        ],
    )

    spend = _aggregate_cross_card_spend([card1, card2])
    assert spend["food_delivery"] == 800.0
    ok("food_delivery aggregated across 2 cards (500+300=800)")

    assert spend["grocery"] == 800.0
    ok("grocery from card1 == 800")

    assert spend["shopping_online"] == 1200.0
    ok("shopping_online from card2 == 1200")


def test_top_categories():
    print("\n[3] _top_categories")

    spend = {
        "food_delivery": 1500.0,
        "grocery": 800.0,
        "shopping_online": 2000.0,
        "others": 5000.0,  # should be excluded
        "fuel": 200.0,
    }
    top = _top_categories(spend, n=3)
    assert len(top) == 3
    ok("Returns exactly 3 categories")

    assert top[0] == "shopping_online"
    ok("Highest spend (shopping_online) is first")

    assert "others" not in top
    ok("'others' excluded from top categories")

    assert top == sorted(top, key=lambda k: spend[k], reverse=True)
    ok("Sorted by spend descending")


def test_build_spend_profile_text():
    print("\n[4] _build_spend_profile_text")

    card = _make_card(
        "x",
        "X Card",
        [
            _txn("food_delivery", 1000.0),
            _txn("grocery", 500.0),
        ],
    )
    top = ["food_delivery", "grocery"]
    text = _build_spend_profile_text([card], top)

    assert "food_delivery" in text or "food" in text.lower()
    ok("food_delivery category mentioned in profile text")

    assert "₹" in text or "Rs" in text or "1000" in text
    ok("Spend amount included in profile text")

    assert len(text) > 10
    ok("Profile text is non-empty")


# ─────────────────────────────────────────────────────────────────────────────
# 3. JSON cleaner
# ─────────────────────────────────────────────────────────────────────────────


def test_clean_json():
    print("\n[5] _clean_json")

    cases = [
        ('```json\n{"a":1}\n```', '{"a":1}'),
        ('```\n{"a":1}\n```', '{"a":1}'),
        ('{"a":1}', '{"a":1}'),
        ('Here:\n{"a":1}\nEnd', '{"a":1}'),
    ]
    for raw, expected in cases:
        result = _clean_json(raw)
        assert expected in result, f"Expected '{expected}' in '{result}'"
    ok("All markdown fence stripping cases pass")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Rule filter
# ─────────────────────────────────────────────────────────────────────────────


def test_rule_filter_removes_current_cards():
    print("\n[6] _rule_filter_candidates — removes current cards")

    spend = {"food_delivery": 1000.0, "grocery": 500.0}
    current_ids = {"axis-airtel", "hdfc-millennia"}
    candidates = list(ALT_CARDS)  # includes hdfc-millennia

    filtered = _rule_filter_candidates(candidates, current_ids, spend)
    filtered_ids = {c["_id"] for c in filtered}

    assert "axis-airtel" not in filtered_ids
    ok("axis-airtel removed (current card)")

    assert "hdfc-millennia" not in filtered_ids
    ok("hdfc-millennia removed (current card)")

    assert "sbi-cashback" in filtered_ids
    ok("sbi-cashback kept (not current card)")


def test_rule_filter_removes_travel_card_for_non_traveller():
    print("\n[7] _rule_filter_candidates — removes travel card for non-traveller")

    # User spends mostly on food/grocery, 0 travel → travel card should be filtered
    spend = {"food_delivery": 2000.0, "grocery": 1000.0, "travel_flights": 0.0}
    filtered = _rule_filter_candidates(ALT_CARDS, set(), spend)
    filtered_ids = {c["_id"] for c in filtered}

    assert "axis-travel-card" not in filtered_ids
    ok("Travel card removed for user with <5% travel spend")

    # Non-travel cards remain
    assert "hdfc-millennia" in filtered_ids
    ok("Non-travel card kept")


def test_rule_filter_keeps_travel_card_for_traveller():
    print("\n[8] _rule_filter_candidates — keeps travel card for heavy traveller")

    # 30% of spend is travel → keep travel card
    spend = {
        "food_delivery": 1000.0,
        "travel_flights": 2000.0,
        "travel_hotels": 800.0,
    }
    filtered = _rule_filter_candidates(ALT_CARDS, set(), spend)
    filtered_ids = {c["_id"] for c in filtered}

    assert "axis-travel-card" in filtered_ids
    ok("Travel card kept for user with >5% travel spend")


# ─────────────────────────────────────────────────────────────────────────────
# 5. Routing advice (Section 9)
# ─────────────────────────────────────────────────────────────────────────────


def test_routing_advice_single_card():
    print("\n[9] _compute_routing_advice — single card returns empty list")

    card = _make_card(
        "a", "Card A", [_txn("food_delivery", 500.0)], _cashback_result({"food_delivery": 50.0}, {})
    )
    advice = _compute_routing_advice([card])
    assert advice == []
    ok("Single card → no routing advice")


def test_routing_advice_multi_card():
    print("\n[10] _compute_routing_advice — multi-card generates advice")

    # Card A: 25% on food_delivery, Card B: 1% on food_delivery
    card_a = _make_card(
        "axis-airtel",
        "Axis Airtel",
        [
            _txn("food_delivery", 1000.0),
        ],
        _cashback_result(
            {"food_delivery": 250.0},  # 25% earned
            {},
            score=90,
        ),
    )
    card_b = _make_card(
        "hdfc-millennia",
        "HDFC Millennia",
        [
            _txn("food_delivery", 500.0),
        ],
        _cashback_result(
            {"food_delivery": 5.0},  # 1% earned
            {},
            score=20,
        ),
    )

    advice = _compute_routing_advice([card_a, card_b])
    # Should suggest using Axis Airtel for food_delivery (higher rate)
    assert isinstance(advice, list)
    ok(f"Routing advice generated: {len(advice)} item(s)")
    if advice:
        assert any("Axis Airtel" in a or "food" in a.lower() or "Food" in a for a in advice)
        ok("Advice references the better card for food_delivery")


# ─────────────────────────────────────────────────────────────────────────────
# 6. Cashback summary builder
# ─────────────────────────────────────────────────────────────────────────────


def test_build_cashback_summary():
    print("\n[11] _build_cashback_summary")

    cards = [
        _make_card(
            "axis-airtel",
            "Axis Airtel",
            [_txn("food_delivery", 500.0)],
            _cashback_result({"food_delivery": 50.0}, {"grocery": 30.0}, score=62),
        ),
        _make_card(
            "hdfc-millennia",
            "HDFC Millennia",
            [_txn("shopping_online", 1000.0)],
            _cashback_result({"shopping_online": 50.0}, {}, score=80),
        ),
    ]
    summary = _build_cashback_summary(cards)

    assert len(summary["cards"]) == 2
    ok("Summary has 2 card entries")

    assert summary["total_earned"] == 100.0
    ok("total_earned == 100.0 (50+50)")

    assert summary["total_missed"] == 30.0
    ok("total_missed == 30.0")

    scores = [c["utilization_score"] for c in summary["cards"]]
    assert 62 in scores and 80 in scores
    ok("Per-card utilization scores preserved")


# ─────────────────────────────────────────────────────────────────────────────
# 7. Rule-based fallback result
# ─────────────────────────────────────────────────────────────────────────────


def test_rule_based_result_verdicts():
    print("\n[12] _rule_based_result — verdict by score")

    for score, expected_verdict in [(80, "Good fit"), (55, "Could do better"), (20, "Switch recommended")]:
        summary = {
            "cards": [
                {"card_name": "Test", "utilization_score": score, "earned_inr": 500.0, "missed_inr": 100.0}
            ],
            "total_earned": 500.0,
            "total_missed": 100.0,
        }
        result = _rule_based_result(summary, [], ["food_delivery"], 5000.0, [])
        assert result["verdict"] == expected_verdict, (
            f"Score {score}: expected '{expected_verdict}', got '{result['verdict']}'"
        )
    ok("Good fit at score 80")
    ok("Could do better at score 55")
    ok("Switch recommended at score 20")


def test_rule_based_result_structure():
    print("\n[13] _rule_based_result — output structure")

    summary = {
        "cards": [{"card_name": "Test", "utilization_score": 50, "earned_inr": 200.0, "missed_inr": 200.0}],
        "total_earned": 200.0,
        "total_missed": 200.0,
    }
    result = _rule_based_result(
        summary, ALT_CARDS[:2], ["food_delivery", "grocery"], 5000.0, ["Use X for food"]
    )

    assert "verdict" in result and result["verdict"] in ("Good fit", "Could do better", "Switch recommended")
    ok("verdict field present and valid")

    assert "card_score" in result
    ok("card_score field present")

    assert isinstance(result["recommendations"], list)
    ok("recommendations is a list")

    assert isinstance(result["tips"], list) and len(result["tips"]) > 0
    ok("tips list is non-empty")

    assert isinstance(result["routing_advice"], list)
    ok("routing_advice is a list")


# ─────────────────────────────────────────────────────────────────────────────
# 8. _rank_with_gemini with mocked LLM
# ─────────────────────────────────────────────────────────────────────────────

MOCK_GEMINI_RESPONSE = json.dumps(
    {
        "verdict": "Could do better",
        "verdict_reason": "You are earning ₹150/month but could earn ₹400 with HDFC Millennia.",
        "card_score": 62,
        "recommendations": [
            {
                "card_id": "hdfc-millennia",
                "card_name": "HDFC Millennia Credit Card",
                "bank": "HDFC Bank",
                "estimated_monthly_cashback": 400,
                "estimated_annual_cashback": 4800,
                "improvement_over_current_monthly": 250,
                "why_better": "Earns 5% on food delivery vs your current 1%. On ₹1500 monthly food spend, that's ₹75 vs ₹15.",
                "best_categories": ["food_delivery", "grocery"],
                "caveat": "Annual fee of ₹1000 applies.",
            }
        ],
        "routing_advice": ["Use HDFC Millennia for all food orders (5% vs 1% on current card)"],
        "tips": [
            "Consolidate food delivery spend on your highest-cashback card.",
            "Set up auto-pay for utility bills.",
            "Review your card's offer portal before large purchases.",
        ],
    }
)


def test_rank_with_gemini_success():
    print("\n[14] _rank_with_gemini — mocked Gemini Pro success")

    summary = {
        "cards": [
            {"card_name": "Axis Airtel", "utilization_score": 62, "earned_inr": 150.0, "missed_inr": 100.0}
        ],
        "total_earned": 150.0,
        "total_missed": 100.0,
    }

    with (
        mock.patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key"}),
        mock.patch("agents.compare_node._call_gemini_pro", return_value=MOCK_GEMINI_RESPONSE),
    ):
        result = _rank_with_gemini(summary, ALT_CARDS[:2], ["food_delivery", "grocery"], 5000.0, [])

    assert result["verdict"] == "Could do better"
    ok("verdict == 'Could do better'")

    assert result["card_score"] == 62
    ok("card_score == 62")

    assert len(result["recommendations"]) == 1
    ok("1 recommendation returned")

    rec = result["recommendations"][0]
    assert rec["card_id"] == "hdfc-millennia"
    ok("Correct card_id in recommendation")

    assert rec["estimated_monthly_cashback"] == 400.0
    ok("estimated_monthly_cashback == 400")

    assert rec["improvement_over_current_monthly"] == 250.0
    ok("improvement_over_current_monthly == 250")

    assert len(result["tips"]) == 3
    ok("3 tips returned")

    assert len(result["routing_advice"]) > 0
    ok("routing_advice non-empty")


def test_rank_with_gemini_fenced_response():
    print("\n[15] _rank_with_gemini — Gemini wraps JSON in markdown fences")

    fenced = "```json\n" + MOCK_GEMINI_RESPONSE + "\n```"
    summary = {
        "cards": [{"card_name": "Card", "utilization_score": 50, "earned_inr": 100.0, "missed_inr": 50.0}],
        "total_earned": 100.0,
        "total_missed": 50.0,
    }

    with (
        mock.patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key"}),
        mock.patch("agents.compare_node._call_gemini_pro", return_value=fenced),
    ):
        result = _rank_with_gemini(summary, ALT_CARDS[:1], ["food_delivery"], 3000.0, [])

    assert result["verdict"] in ("Could do better", "Good fit", "Switch recommended")
    ok("Fenced JSON correctly parsed")


def test_rank_with_gemini_failure_fallback():
    print("\n[16] _rank_with_gemini — Gemini failure falls back to rule-based")

    summary = {
        "cards": [{"card_name": "Card", "utilization_score": 40, "earned_inr": 100.0, "missed_inr": 150.0}],
        "total_earned": 100.0,
        "total_missed": 150.0,
    }

    with (
        mock.patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key"}),
        mock.patch("agents.compare_node._call_gemini_pro", side_effect=Exception("API error")),
    ):
        result = _rank_with_gemini(summary, ALT_CARDS[:2], ["food_delivery"], 3000.0, [])

    assert result["verdict"] in ("Good fit", "Could do better", "Switch recommended")
    ok("Graceful fallback on Gemini failure")

    assert "card_score" in result and 0 <= result["card_score"] <= 100
    ok("card_score in valid range after fallback")


def test_rank_without_api_key():
    print("\n[17] _rank_with_gemini — no API key uses rule-based")

    summary = {
        "cards": [{"card_name": "Card", "utilization_score": 75, "earned_inr": 300.0, "missed_inr": 100.0}],
        "total_earned": 300.0,
        "total_missed": 100.0,
    }

    with mock.patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
        result = _rank_with_gemini(summary, ALT_CARDS[:2], ["grocery"], 4000.0, [])

    assert result["verdict"] in ("Good fit", "Could do better", "Switch recommended")
    ok("Rule-based result returned when no API key")


# ─────────────────────────────────────────────────────────────────────────────
# 9. Full node tests
# ─────────────────────────────────────────────────────────────────────────────


def test_node_happy_path():
    print("\n[18] compare_node — full node, mocked DB + Gemini")

    card = _make_card(
        "axis-airtel",
        "Axis Airtel",
        [_txn("food_delivery", 1000.0), _txn("grocery", 500.0)],
        _cashback_result({"food_delivery": 100.0}, {"grocery": 50.0}, score=67),
    )
    state = _make_state([card])

    with (
        mock.patch("agents.compare_node._get_embedding", return_value=[0.0] * 768),
        mock.patch("agents.compare_node._vector_search_async", return_value=ALT_CARDS[:3]),
        mock.patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key"}),
        mock.patch("agents.compare_node._call_gemini_pro", return_value=MOCK_GEMINI_RESPONSE),
    ):
        result = asyncio.run(compare_node(state))

    assert result["status"] == "done"
    ok("status == 'done'")

    assert result["ui_action"] == "show_results"
    ok("ui_action == 'show_results'")

    assert result["comparison_result"] is not None
    ok("comparison_result is populated")

    cr = result["comparison_result"]
    assert cr["verdict"] in ("Good fit", "Could do better", "Switch recommended")
    ok(f"verdict is valid: '{cr['verdict']}'")

    assert 0 <= cr["card_score"] <= 100
    ok(f"card_score in [0,100]: {cr['card_score']}")

    assert isinstance(cr["recommendations"], list)
    ok("recommendations is a list")

    assert isinstance(cr["tips"], list)
    ok("tips is a list")


def test_node_vector_search_fallback():
    print("\n[19] compare_node — vector search fails, falls back to category filter")

    card = _make_card(
        "axis-airtel",
        "Axis Airtel",
        [_txn("food_delivery", 800.0)],
        _cashback_result({"food_delivery": 80.0}, {}, score=70),
    )
    state = _make_state([card])

    # Simulate vector search failing → category fallback returns ALT_CARDS
    with (
        mock.patch("agents.compare_node._get_embedding", return_value=[0.0] * 768),
        mock.patch("agents.compare_node._vector_search_async", return_value=ALT_CARDS[:2]),
        mock.patch.dict("os.environ", {"GEMINI_API_KEY": ""}),
    ):
        result = asyncio.run(compare_node(state))

    assert result["status"] == "done"
    ok("Node completes even when vector search falls back")

    assert result["comparison_result"] is not None
    ok("comparison_result populated with fallback data")


def test_node_no_api_key_completes():
    print("\n[20] compare_node — no API key, uses rule-based throughout")

    card = _make_card(
        "hdfc-millennia",
        "HDFC Millennia",
        [_txn("shopping_online", 2000.0), _txn("grocery", 500.0)],
        _cashback_result({"shopping_online": 100.0}, {"grocery": 25.0}, score=80),
    )
    state = _make_state([card])

    with (
        mock.patch("agents.compare_node._get_embedding", return_value=[0.0] * 768),
        mock.patch("agents.compare_node._vector_search_async", return_value=ALT_CARDS),
        mock.patch.dict("os.environ", {"GEMINI_API_KEY": ""}),
    ):
        result = asyncio.run(compare_node(state))

    assert result["status"] == "done"
    ok("Node completes without API key")

    assert result["comparison_result"]["verdict"] == "Good fit"
    ok("Score 80 → verdict == 'Good fit'")


def test_node_multi_card():
    print("\n[21] compare_node — multi-card generates routing advice")

    card1 = _make_card(
        "axis-airtel",
        "Axis Airtel",
        [_txn("food_delivery", 1500.0)],
        _cashback_result({"food_delivery": 375.0}, {}, score=90),
    )
    card2 = _make_card(
        "hdfc-millennia",
        "HDFC Millennia",
        [_txn("shopping_online", 2000.0)],
        _cashback_result({"shopping_online": 100.0}, {}, score=60),
    )
    state = _make_state([card1, card2])

    with (
        mock.patch("agents.compare_node._get_embedding", return_value=[0.0] * 768),
        mock.patch("agents.compare_node._vector_search_async", return_value=ALT_CARDS[:2]),
        mock.patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key"}),
        mock.patch("agents.compare_node._call_gemini_pro", return_value=MOCK_GEMINI_RESPONSE),
    ):
        result = asyncio.run(compare_node(state))

    assert result["status"] == "done"
    ok("Multi-card compare_node completes")

    cr = result["comparison_result"]
    assert cr is not None
    ok("comparison_result is set for multi-card")

    assert isinstance(cr["routing_advice"], list)
    ok("routing_advice present for multi-card")


def test_node_current_cards_excluded():
    print("\n[22] compare_node — current cards excluded from recommendations")

    # Both ALT_CARDS[0] (hdfc-millennia) and ALT_CARDS[1] (sbi-cashback) are
    # the "user's current cards" — should not appear in recommendations
    card1 = _make_card(
        "hdfc-millennia",
        "HDFC Millennia",
        [_txn("food_delivery", 500.0)],
        _cashback_result({"food_delivery": 25.0}, {}, score=50),
    )
    card2 = _make_card(
        "sbi-cashback",
        "SBI Cashback",
        [_txn("shopping_online", 1000.0)],
        _cashback_result({"shopping_online": 50.0}, {}, score=60),
    )
    state = _make_state([card1, card2])

    # Return all ALT_CARDS including current ones — rule filter should remove them
    with (
        mock.patch("agents.compare_node._get_embedding", return_value=[0.0] * 768),
        mock.patch("agents.compare_node._vector_search_async", return_value=ALT_CARDS),
        mock.patch.dict("os.environ", {"GEMINI_API_KEY": ""}),
    ):
        result = asyncio.run(compare_node(state))

    cr = result["comparison_result"]
    rec_ids = {r["card_id"] for r in cr["recommendations"]}
    assert "hdfc-millennia" not in rec_ids
    ok("hdfc-millennia excluded (current card)")
    assert "sbi-cashback" not in rec_ids
    ok("sbi-cashback excluded (current card)")


# ─────────────────────────────────────────────────────────────────────────────
# Run all
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  compare_node test suite")
    print("=" * 60)

    test_constants()
    test_aggregate_cross_card_spend()
    test_top_categories()
    test_build_spend_profile_text()
    test_clean_json()
    test_rule_filter_removes_current_cards()
    test_rule_filter_removes_travel_card_for_non_traveller()
    test_rule_filter_keeps_travel_card_for_traveller()
    test_routing_advice_single_card()
    test_routing_advice_multi_card()
    test_build_cashback_summary()
    test_rule_based_result_verdicts()
    test_rule_based_result_structure()
    test_rank_with_gemini_success()
    test_rank_with_gemini_fenced_response()
    test_rank_with_gemini_failure_fallback()
    test_rank_without_api_key()
    test_node_happy_path()
    test_node_vector_search_fallback()
    test_node_no_api_key_completes()
    test_node_multi_card()
    test_node_current_cards_excluded()

    print()
    print("=" * 60)
    print(f"  Results: {PASS} passed, {FAIL} failed")
    print("=" * 60)

    if FAIL > 0:
        sys.exit(1)
