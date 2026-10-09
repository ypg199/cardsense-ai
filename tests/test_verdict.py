"""compare_node.reconcile_result: computed estimates and a verdict that matches the score."""

from __future__ import annotations

import pytest

from agents.compare_node import estimate_card_on_spend, reconcile_result
from tests.test_compare_node import _cashback_result, _make_card, _txn

FIVE_PCT_FOOD = {
    "_id": "food-card",
    "name": "Food Card",
    "bank": "Bank A",
    "annual_fee": 500,
    "benefits": [
        {"category": "food_delivery", "rate": 0.05},
        {"category": "others", "rate": 0.01},
    ],
}
ONE_PCT = {
    "_id": "plain",
    "name": "Plain Card",
    "bank": "Bank B",
    "benefits": [{"category": "others", "rate": 0.01}],
}

MODEL = {
    "verdict": "Switch recommended",
    "verdict_reason": "model text",
    "card_score": 12,
    "recommendations": [
        {
            "card_id": "food-card",
            "card_name": "Food Card",
            "bank": "Bank A",
            "estimated_monthly_cashback": 9999,
            "estimated_annual_cashback": 9999,
            "improvement_over_current_monthly": 9999,
            "why_better": "Model explanation.",
            "best_categories": ["food_delivery"],
            "caveat": None,
        }
    ],
    "routing_advice": [],
    "tips": ["tip"],
}


def _card(score, earned, months=("2024-01",)):
    txns = [_txn("food_delivery", 10000.0, m) for m in months]
    card = _make_card("mine", "My Card", txns, _cashback_result(earned, {}, score=score))
    card["months"] = list(months)
    return card


def test_estimate_is_monthly_and_uses_the_real_rates():
    card = _card(100, {"food_delivery": 200.0}, months=("2024-01", "2024-02"))
    est = estimate_card_on_spend(FIVE_PCT_FOOD, [card])
    assert est["monthly"] == pytest.approx(500.0)  # 5% of 10,000 per month, not 1,000 for both
    assert est["annual"] == pytest.approx(6000.0)
    assert est["by_category"] == {"food_delivery": 500.0}


def test_full_score_with_a_much_better_card_says_so_without_contradicting_the_score():
    out = reconcile_result(MODEL, [_card(100, {"food_delivery": 100.0})], [FIVE_PCT_FOOD])
    assert out["verdict"] == "Switch recommended"
    assert out["card_score"] == 100  # the gauge's score, not the model's
    assert out["verdict_reason"].startswith("You're using your card well")
    rec = out["recommendations"][0]
    assert rec["estimated_monthly_cashback"] == 500.0  # computed, not the model's 9999
    assert rec["improvement_over_current_monthly"] == 400.0
    assert rec["why_better"] == "Model explanation."  # model wording is kept
    assert out["tips"] == ["tip"]


def test_good_fit_when_nothing_earns_more():
    out = reconcile_result(MODEL, [_card(90, {"food_delivery": 500.0})], [FIVE_PCT_FOOD, ONE_PCT])
    assert out["verdict"] == "Good fit"
    assert out["recommendations"] == []  # equal or worse cards are not recommended
    assert "90%" in out["verdict_reason"]


def test_low_score_without_a_better_card_is_could_do_better():
    out = reconcile_result({**MODEL, "recommendations": []}, [_card(40, {"food_delivery": 500.0})], [ONE_PCT])
    assert out["verdict"] == "Could do better"
    assert out["card_score"] == 40


def test_small_gain_is_not_a_switch():
    # 120/month more is below the switch threshold, so the card is listed but the verdict stays
    out = reconcile_result(MODEL, [_card(85, {"food_delivery": 380.0})], [FIVE_PCT_FOOD])
    assert out["recommendations"][0]["improvement_over_current_monthly"] == 120.0
    assert out["verdict"] == "Good fit"


def test_recommendations_sorted_by_gain():
    rich = {
        **FIVE_PCT_FOOD,
        "_id": "rich",
        "name": "Rich",
        "benefits": [{"category": "food_delivery", "rate": 0.1}],
    }
    out = reconcile_result(MODEL, [_card(50, {"food_delivery": 100.0})], [FIVE_PCT_FOOD, rich])
    assert [r["card_id"] for r in out["recommendations"]] == ["rich", "food-card"]
    assert out["recommendations"][1]["why_better"] == "Model explanation."
    assert "food delivery" in out["recommendations"][0]["why_better"]  # computed fallback text


def test_comparison_puts_your_card_first_then_alternatives_by_earnings():
    rich = {
        **FIVE_PCT_FOOD,
        "_id": "rich",
        "name": "Rich",
        "annual_fee": 3000,
        "benefits": [{"category": "food_delivery", "rate": 0.1}],
    }
    card = _card(100, {"food_delivery": 100.0}, months=("2024-01", "2024-02"))
    card["cashback_result"]["earned_breakdown"] = {"food_delivery": 200.0}  # 100 a month
    out = reconcile_result(
        MODEL, [card], [ONE_PCT, FIVE_PCT_FOOD, rich], {"mine": {"annual_fee": 500, "bank": "My Bank"}}
    )
    table = out["comparison"]
    assert [c["card_id"] for c in table["cards"]] == ["mine", "rich", "food-card", "plain"]
    mine, rich_col = table["cards"][0], table["cards"][1]
    assert mine["is_current"] and mine["monthly_cashback"] == 100.0 and mine["net_annual"] == 700.0
    assert rich_col["monthly_cashback"] == 1000.0 and rich_col["net_annual"] == 12000.0 - 3000.0
    assert table["categories"] == [{"category": "food_delivery", "monthly_spend": 10000.0}]
    # cards that earn less still appear in the comparison, just not as recommendations
    assert "plain" not in [r["card_id"] for r in out["recommendations"]]


def test_comparison_without_candidates_shows_just_your_card():
    out = reconcile_result({**MODEL, "recommendations": []}, [_card(80, {"food_delivery": 100.0})], [])
    assert [c["card_id"] for c in out["comparison"]["cards"]] == ["mine"]
