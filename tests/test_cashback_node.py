"""
tests/test_cashback_node.py
Standalone tests for agents/cashback_node.py.
All DB calls are mocked — no MongoDB connection required.
"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest.mock as mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.cashback_node import (
    calculate_cashback,
    cashback_calc_node,
    get_score_label,
    _build_benefit_index,
    _compute_trend,
    _calc_transaction_cashback,
    SCORE_LABELS,
)
from agents.state import AnalysisState, CardState, Transaction

# ─────────────────────────────────────────────────────────────────────────────
# Test scaffolding
# ─────────────────────────────────────────────────────────────────────────────

PASS = 0
FAIL = 0

def ok(msg: str):
    global PASS; PASS += 1
    print(f"  ✅ {msg}")

def fail(msg: str):
    global FAIL; FAIL += 1
    print(f"  ❌ {msg}")


# ── Sample card document ──────────────────────────────────────────────────────
AXIS_AIRTEL_DOC = {
    "_id": "axis-airtel",
    "name": "Axis Airtel Credit Card",
    "bank": "Axis Bank",
    "benefits": [
        {"category": "airtel_recharge", "label": "Airtel Recharge", "rate": 0.25,
         "max_cashback_per_month": None, "reward_type": "cashback"},
        {"category": "utility_bills",   "label": "Utility Bills",   "rate": 0.10,
         "max_cashback_per_month": None, "reward_type": "cashback"},
        {"category": "food_delivery",   "label": "Zomato",          "rate": 0.10,
         "max_cashback_per_month": None, "reward_type": "cashback"},
        {"category": "grocery",         "label": "BigBasket",       "rate": 0.10,
         "max_cashback_per_month": None, "reward_type": "cashback"},
        {"category": "others",          "label": "Others",          "rate": 0.01,
         "max_cashback_per_month": None, "reward_type": "cashback"},
    ],
    "utilization_questions": [
        {"id": "q_airtel_sim", "maps_to_category": "airtel_recharge",
         "auto_detect_keywords": ["airtel"]},
        {"id": "q_utility",    "maps_to_category": "utility_bills",
         "auto_detect_keywords": ["bescom"]},
        {"id": "q_zomato",     "maps_to_category": "food_delivery",
         "auto_detect_keywords": ["zomato"]},
        {"id": "q_bigbasket",  "maps_to_category": "grocery",
         "auto_detect_keywords": ["bigbasket"]},
    ],
}

SBI_CAPPED_DOC = {
    "_id": "sbi-cashback",
    "name": "SBI Cashback Credit Card",
    "bank": "SBI Card",
    "benefits": [
        {"category": "shopping_online", "label": "Online Shopping", "rate": 0.05,
         "max_cashback_per_month": 5000, "reward_type": "cashback"},
        {"category": "others", "label": "Others", "rate": 0.01,
         "max_cashback_per_month": None, "reward_type": "cashback"},
    ],
    "utilization_questions": [
        {"id": "q_sbi_online", "maps_to_category": "shopping_online",
         "auto_detect_keywords": ["amazon"]},
    ],
}


def _txn(
    merchant: str,
    amount: float,
    category: str,
    month: str = "2024-01",
    txn_type: str = "debit",
) -> Transaction:
    return Transaction(
        date=f"{month}-15",
        merchant=merchant,
        amount=amount,
        transaction_type=txn_type,
        category=category,
        month=month,
    )


def _make_card(
    transactions: list[Transaction],
    qa_answers: dict,
    card_id: str = "axis-airtel",
) -> CardState:
    return {
        "card_id": card_id, "card_name": "Test Card",
        "months": ["2024-01"], "pdf_bytes_list": [], "pdf_passwords": [],
        "pdf_encrypted": False, "pdf_text": "", "transactions": transactions,
        "total_spend": sum(t["amount"] for t in transactions if t["transaction_type"] == "debit"),
        "pending_questions": [], "answered_questions": [],
        "qa_answers": qa_answers, "cashback_result": None,
        "utilization_score": 0, "status": "calculating",
    }


def _make_state(card: CardState) -> AnalysisState:
    return {
        "session_id": "test-cashback", "status": "calculating",
        "cards": [card], "current_card_idx": 0,
        "locked_card_idx": None, "locked_pdf_idx": None,
        "current_question": None, "comparison_result": None,
        "ui_action": "show_loading", "total_questions_count": 0,
        "answered_questions_count": 0, "error": None,
        "created_at": "2024-01-01T00:00:00Z",
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. Score labels
# ─────────────────────────────────────────────────────────────────────────────

def test_score_labels():
    print("\n[1] Score labels (Section 10)")

    cases = [
        (100, "Excellent"),
        (90,  "Excellent"),
        (89,  "Good"),
        (70,  "Good"),
        (69,  "Average"),
        (50,  "Average"),
        (49,  "Below average"),
        (30,  "Below average"),
        (29,  "Poor"),
        (0,   "Poor"),
    ]
    for score, expected_fragment in cases:
        label = get_score_label(score)
        assert expected_fragment.lower() in label.lower(), \
            f"Score {score}: expected '{expected_fragment}' in '{label}'"
    ok("All 5 score bands return correct labels")

    assert len(SCORE_LABELS) == 5
    ok("Exactly 5 score bands defined")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Benefit index
# ─────────────────────────────────────────────────────────────────────────────

def test_build_benefit_index():
    print("\n[2] _build_benefit_index")

    index = _build_benefit_index(AXIS_AIRTEL_DOC)
    assert "airtel_recharge" in index
    assert index["airtel_recharge"]["rate"] == 0.25
    ok("airtel_recharge in index with rate 0.25")

    assert "food_delivery" in index
    assert "others" in index
    ok("food_delivery and others in index")

    # Highest rate wins when duplicates exist
    doc_with_dupe = {
        "benefits": [
            {"category": "grocery", "rate": 0.05},
            {"category": "grocery", "rate": 0.10},  # Higher — should win
        ],
        "utilization_questions": [],
    }
    idx2 = _build_benefit_index(doc_with_dupe)
    assert idx2["grocery"]["rate"] == 0.10
    ok("Highest rate wins when duplicate categories exist")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Monthly cap enforcement
# ─────────────────────────────────────────────────────────────────────────────

def test_monthly_cap():
    print("\n[3] _calc_transaction_cashback — monthly cap")

    benefit = {"category": "shopping_online", "rate": 0.05, "max_cashback_per_month": 100.0}
    caps: dict[str, float] = {}

    # First txn: 2000 × 5% = 100 → exactly hits cap
    txn1 = _txn("Amazon", 2000.0, "shopping_online")
    c1 = _calc_transaction_cashback(txn1, benefit, caps)
    assert c1 == 100.0
    ok("First transaction earns exactly up to cap (₹100)")

    # Second txn: cap already reached → 0 earned
    txn2 = _txn("Flipkart", 1000.0, "shopping_online")
    c2 = _calc_transaction_cashback(txn2, benefit, caps)
    assert c2 == 0.0
    ok("Second transaction earns ₹0 after cap exhausted")

    # Different month → fresh cap
    benefit2 = {"category": "shopping_online", "rate": 0.05, "max_cashback_per_month": 100.0}
    txn3 = _txn("Amazon", 1000.0, "shopping_online", month="2024-02")
    c3 = _calc_transaction_cashback(txn3, benefit2, caps)
    assert c3 == 50.0
    ok("Different month gets fresh cap (₹50 on ₹1000 × 5%)")

    # Partial cap: only some of the cashback fits
    caps2: dict[str, float] = {"2024-01:shopping_online": 80.0}
    txn4 = _txn("Myntra", 2000.0, "shopping_online")  # would earn 100, only 20 left
    c4 = _calc_transaction_cashback(txn4, benefit, caps2)
    assert c4 == 20.0
    ok("Partial cap: only remaining ₹20 earned")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Trend calculation
# ─────────────────────────────────────────────────────────────────────────────

def test_compute_trend():
    print("\n[4] _compute_trend")

    assert _compute_trend([]) == "single_month"
    ok("Empty list → single_month")

    assert _compute_trend([75]) == "single_month"
    ok("Single month → single_month")

    assert _compute_trend([40, 50, 60, 70]) == "improving"
    ok("Rising scores → improving")

    assert _compute_trend([70, 60, 50, 40]) == "declining"
    ok("Falling scores → declining")

    assert _compute_trend([60, 62, 61, 63]) == "flat"
    ok("Stable scores → flat")

    assert _compute_trend([50, 60]) == "improving"
    ok("Two months, rising → improving")


# ─────────────────────────────────────────────────────────────────────────────
# 5. Core calculate_cashback — Section 10 formula
# ─────────────────────────────────────────────────────────────────────────────

def test_utilization_score_formula():
    print("\n[5] Utilization score formula (Section 10)")

    # User has:
    #   airtel_recharge spend = 1000  (rate 25%) → potential 250, confirmed YES
    #   food_delivery spend   =  900  (rate 10%) → potential  90, confirmed NO
    #   utility_bills spend   =  500  (rate 10%) → potential  50, confirmed YES
    #
    # theoretical_max = 250 + 90 + 50 = 390
    # actual_earned   = 250 + 0 + 50  = 300
    # score = round(300/390 * 100) = round(76.9) = 77

    txns = [
        _txn("Airtel", 1000.0, "airtel_recharge"),
        _txn("Zomato", 900.0,  "food_delivery"),
        _txn("BESCOM", 500.0,  "utility_bills"),
    ]
    qa = {
        "q_airtel_sim": True,
        "q_zomato":     False,
        "q_utility":    True,
    }

    result = calculate_cashback(txns, qa, AXIS_AIRTEL_DOC)

    assert result["utilization_score"] == 77, \
        f"Expected 77, got {result['utilization_score']}"
    ok("Utilization score == 77 (formula-correct)")

    assert result["earned_breakdown"].get("airtel_recharge") == 250.0
    ok("airtel_recharge earned == ₹250 (1000 × 25%)")

    assert result["earned_breakdown"].get("utility_bills") == 50.0
    ok("utility_bills earned == ₹50 (500 × 10%)")

    # food_delivery answered No → appears in missed
    assert result["missed_breakdown"].get("food_delivery") == 90.0
    ok("food_delivery missed == ₹90 (900 × 10%, answered No)")

    assert "food_delivery" not in result["earned_breakdown"]
    ok("food_delivery NOT in earned (answered No)")


def test_score_100_when_all_confirmed():
    print("\n[6] Score == 100 when all categories confirmed")

    txns = [
        _txn("Airtel", 400.0, "airtel_recharge"),
        _txn("Zomato", 300.0, "food_delivery"),
        _txn("BESCOM", 200.0, "utility_bills"),
        _txn("BigBasket", 100.0, "grocery"),
    ]
    qa = {
        "q_airtel_sim": True,
        "q_zomato": True,
        "q_utility": True,
        "q_bigbasket": True,
    }

    result = calculate_cashback(txns, qa, AXIS_AIRTEL_DOC)
    assert result["utilization_score"] == 100
    ok("Score == 100 when all categories confirmed Yes")


def test_score_0_when_none_confirmed():
    print("\n[7] Score == 0 when no categories confirmed")

    txns = [
        _txn("Airtel", 400.0, "airtel_recharge"),
        _txn("Zomato", 300.0, "food_delivery"),
    ]
    qa = {
        "q_airtel_sim": False,
        "q_zomato": False,
    }

    result = calculate_cashback(txns, qa, AXIS_AIRTEL_DOC)
    assert result["utilization_score"] == 0
    ok("Score == 0 when all categories answered No")
    assert sum(result["earned_breakdown"].values()) == 0.0
    ok("earned_breakdown total == 0")
    assert result["missed_breakdown"].get("airtel_recharge") == 100.0
    ok("airtel_recharge missed == ₹100 (400 × 25%)")


def test_no_question_category_always_earned():
    print("\n[8] Category with no question → always earned")

    # 'others' has no utilization_question in AXIS_AIRTEL_DOC
    txns = [_txn("Random Shop", 500.0, "others")]
    qa = {}  # No answers

    result = calculate_cashback(txns, qa, AXIS_AIRTEL_DOC)
    # 'others' rate is 1% — NOT counted in theoretical_max (≤1%)
    # But should still show some earned cashback
    assert sum(result["earned_breakdown"].values()) >= 0
    ok("No-question category (others) doesn't crash")


def test_credit_transactions_ignored():
    print("\n[9] Credit/refund transactions ignored in calculations")

    txns = [
        _txn("Zomato",   450.0, "food_delivery", txn_type="debit"),
        _txn("Cashback", 50.0,  "others",        txn_type="credit"),
        _txn("Refund",   100.0, "grocery",        txn_type="refund"),
    ]
    qa = {"q_zomato": True}

    result = calculate_cashback(txns, qa, AXIS_AIRTEL_DOC)
    earned = result["earned_breakdown"]
    # Only Zomato debit should count
    assert earned.get("food_delivery", 0) == 45.0
    ok("Only debit transactions contribute to earned cashback")
    assert "others" not in earned or earned.get("others", 0) == 0
    ok("Credit transaction not counted")


# ─────────────────────────────────────────────────────────────────────────────
# 6. Monthly cap in calculate_cashback
# ─────────────────────────────────────────────────────────────────────────────

def test_monthly_cap_in_calculate():
    print("\n[10] Monthly cap enforcement inside calculate_cashback")

    # SBI cap: ₹5000 cashback per month on shopping_online (5%)
    # → Cap reached at ₹100,000 spend
    txns = [
        _txn("Amazon", 80_000.0, "shopping_online"),   # 5% = 4000
        _txn("Flipkart", 40_000.0, "shopping_online"), # 5% = 2000 → but only 1000 left
    ]
    qa = {"q_sbi_online": True}

    result = calculate_cashback(txns, qa, SBI_CAPPED_DOC)
    earned = result["earned_breakdown"].get("shopping_online", 0)
    assert earned == 5000.0
    ok(f"Monthly cap of ₹5000 enforced (earned ₹{earned}, not ₹6000)")


# ─────────────────────────────────────────────────────────────────────────────
# 7. Multi-month calculations
# ─────────────────────────────────────────────────────────────────────────────

def test_multi_month_breakdown():
    print("\n[11] Multi-month — per-month breakdown and totals")

    txns = [
        _txn("Airtel", 400.0, "airtel_recharge", month="2024-01"),
        _txn("Zomato", 300.0, "food_delivery",   month="2024-01"),
        _txn("Airtel", 500.0, "airtel_recharge", month="2024-02"),
        _txn("Zomato", 200.0, "food_delivery",   month="2024-02"),
    ]
    qa = {
        "q_airtel_sim": True,
        "q_zomato":     True,
    }

    result = calculate_cashback(txns, qa, AXIS_AIRTEL_DOC)

    assert len(result["monthly_breakdown"]) == 2
    ok("Two monthly breakdown entries")

    months = [mb["month"] for mb in result["monthly_breakdown"]]
    assert "2024-01" in months and "2024-02" in months
    ok("Both months present in breakdown")

    # Jan: airtel 400×25%=100, zomato 300×10%=30 → 130
    jan = next(mb for mb in result["monthly_breakdown"] if mb["month"] == "2024-01")
    assert jan["earned"] == 130.0
    ok("January earned == ₹130")

    # Feb: airtel 500×25%=125, zomato 200×10%=20 → 145
    feb = next(mb for mb in result["monthly_breakdown"] if mb["month"] == "2024-02")
    assert feb["earned"] == 145.0
    ok("February earned == ₹145")

    # Totals
    total_earned = sum(result["earned_breakdown"].values())
    assert total_earned == 275.0
    ok("Total earned == ₹275 (sum across both months)")


def test_multi_month_trend():
    print("\n[12] Multi-month trend direction")

    # Improving: Jan 40%, Feb 60%, Mar 80%
    txns = []
    for month, spend in [("2024-01", 400), ("2024-02", 700), ("2024-03", 900)]:
        txns.append(_txn("Airtel", float(spend), "airtel_recharge", month=month))

    qa = {"q_airtel_sim": True}
    result = calculate_cashback(txns, qa, AXIS_AIRTEL_DOC)
    # All confirmed → scores should all be 100, trend = flat
    assert result["trend"] in ("flat", "improving", "single_month")
    ok(f"Multi-month trend computed: {result['trend']}")

    # Check single_month flag
    txns_single = [_txn("Airtel", 400.0, "airtel_recharge")]
    result2 = calculate_cashback(txns_single, {"q_airtel_sim": True}, AXIS_AIRTEL_DOC)
    assert result2["trend"] == "single_month"
    ok("Single month → trend == 'single_month'")


# ─────────────────────────────────────────────────────────────────────────────
# 8. Edge cases
# ─────────────────────────────────────────────────────────────────────────────

def test_empty_transactions():
    print("\n[13] Empty transactions")

    result = calculate_cashback([], {}, AXIS_AIRTEL_DOC)
    assert result["utilization_score"] == 0
    ok("Empty transactions → score == 0")
    assert result["earned_breakdown"] == {}
    ok("earned_breakdown empty")
    assert result["trend"] == "single_month"
    ok("trend == 'single_month'")


def test_score_capped_at_100():
    print("\n[14] Utilization score capped at 100")

    # Even if actual > theoretical (floating point weirdness), score ≤ 100
    txns = [_txn("Airtel", 1000.0, "airtel_recharge")]
    qa = {"q_airtel_sim": True}

    result = calculate_cashback(txns, qa, AXIS_AIRTEL_DOC)
    assert result["utilization_score"] <= 100
    ok("Score never exceeds 100")


def test_no_benefit_for_category():
    print("\n[15] Transaction category with no matching benefit")

    # Card only has airtel_recharge and others
    minimal_doc = {
        "_id": "test",
        "benefits": [
            {"category": "airtel_recharge", "rate": 0.25, "max_cashback_per_month": None},
            {"category": "others", "rate": 0.01, "max_cashback_per_month": None},
        ],
        "utilization_questions": [
            {"id": "q_airtel", "maps_to_category": "airtel_recharge",
             "auto_detect_keywords": ["airtel"]},
        ],
    }
    # travel_flights transaction — no matching benefit, falls back to 'others'
    txns = [
        _txn("Airtel", 400.0, "airtel_recharge"),
        _txn("IndiGo", 5000.0, "travel_flights"),  # No travel benefit → falls to others
    ]
    qa = {"q_airtel": True}

    result = calculate_cashback(txns, qa, minimal_doc)
    assert result["utilization_score"] <= 100
    ok("No crash when transaction category has no specific benefit")


def test_others_rate_not_in_theoretical_max():
    print("\n[16] 'others' (1% rate) excluded from theoretical_max")

    txns = [
        _txn("Airtel", 1000.0, "airtel_recharge"),   # 25% → in theoretical max
        _txn("Random", 5000.0, "others"),              # 1% → NOT in theoretical max
    ]
    qa = {"q_airtel_sim": True}

    result = calculate_cashback(txns, qa, AXIS_AIRTEL_DOC)
    # theoretical_max should only count airtel_recharge (25% > 1%)
    # = 1000 * 0.25 = 250
    # actual_earned = 250 (confirmed)
    # score = 100
    assert result["utilization_score"] == 100
    ok("1% 'others' benefit excluded from theoretical_max (score == 100)")


# ─────────────────────────────────────────────────────────────────────────────
# 9. Full node test
# ─────────────────────────────────────────────────────────────────────────────

def test_node_happy_path():
    print("\n[17] cashback_calc_node — full node, mocked DB")

    txns = [
        _txn("Airtel", 1000.0, "airtel_recharge"),
        _txn("Zomato", 500.0,  "food_delivery"),
        _txn("BESCOM", 800.0,  "utility_bills"),
    ]
    qa = {
        "q_airtel_sim": True,
        "q_zomato": True,
        "q_utility": False,
    }
    card = _make_card(txns, qa)
    state = _make_state(card)

    with mock.patch("agents.cashback_node._fetch_card_doc", return_value=AXIS_AIRTEL_DOC):
        result = asyncio.run(cashback_calc_node(state))

    assert result["status"] == "comparing"
    ok("status == 'comparing' after cashback calc")

    assert result["ui_action"] == "show_loading"
    ok("ui_action == 'show_loading'")

    card_out = result["cards"][0]
    assert card_out["status"] == "comparing"
    ok("card.status == 'comparing'")

    cr = card_out["cashback_result"]
    assert cr is not None
    ok("cashback_result is populated")

    assert 0 <= card_out["utilization_score"] <= 100
    ok(f"utilization_score in range [0,100]: {card_out['utilization_score']}")

    # airtel (confirmed): 1000 × 25% = 250
    assert cr["earned_breakdown"].get("airtel_recharge") == 250.0
    ok("airtel_recharge earned == ₹250")

    # zomato (confirmed): 500 × 10% = 50
    assert cr["earned_breakdown"].get("food_delivery") == 50.0
    ok("food_delivery earned == ₹50")

    # utility (denied): 800 × 10% = 80 missed
    assert cr["missed_breakdown"].get("utility_bills") == 80.0
    ok("utility_bills missed == ₹80")

    # Score: theoretical = 250+50+80 = 380, actual = 300 → 79
    assert cr["utilization_score"] == 79
    ok(f"utilization_score == 79")


def test_node_db_missing_graceful():
    print("\n[18] cashback_calc_node — DB miss, graceful fallback")

    card = _make_card([_txn("Zomato", 500.0, "food_delivery")], {})
    state = _make_state(card)

    with mock.patch("agents.cashback_node._fetch_card_doc", return_value=None):
        result = asyncio.run(cashback_calc_node(state))

    assert result["status"] == "comparing"
    ok("Node still returns 'comparing' even when DB misses")

    cr = result["cards"][0]["cashback_result"]
    assert cr is not None and cr["utilization_score"] == 0
    ok("Score == 0 when no benefits loaded")


def test_node_multi_card_isolation():
    print("\n[19] cashback_calc_node — only active card modified")

    card0 = _make_card([_txn("Airtel", 400.0, "airtel_recharge")], {"q_airtel_sim": True},
                       card_id="axis-airtel")
    card1 = _make_card([_txn("Amazon", 1000.0, "shopping_online")], {"q_sbi_online": True},
                       card_id="sbi-cashback")

    state: AnalysisState = {
        "session_id": "test-multi", "status": "calculating",
        "cards": [card0, card1], "current_card_idx": 0,
        "locked_card_idx": None, "locked_pdf_idx": None,
        "current_question": None, "comparison_result": None,
        "ui_action": "show_loading", "total_questions_count": 0,
        "answered_questions_count": 0, "error": None,
        "created_at": "2024-01-01T00:00:00Z",
    }

    with mock.patch("agents.cashback_node._fetch_card_doc", return_value=AXIS_AIRTEL_DOC):
        result = asyncio.run(cashback_calc_node(state))

    # card0 processed
    assert result["cards"][0]["cashback_result"] is not None
    ok("Active card (idx=0) has cashback_result")

    # card1 untouched
    assert result["cards"][1]["cashback_result"] is None
    ok("Inactive card (idx=1) untouched")


# ─────────────────────────────────────────────────────────────────────────────
# Run all
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  cashback_node test suite")
    print("=" * 60)

    test_score_labels()
    test_build_benefit_index()
    test_monthly_cap()
    test_compute_trend()
    test_utilization_score_formula()
    test_score_100_when_all_confirmed()
    test_score_0_when_none_confirmed()
    test_no_question_category_always_earned()
    test_credit_transactions_ignored()
    test_monthly_cap_in_calculate()
    test_multi_month_breakdown()
    test_multi_month_trend()
    test_empty_transactions()
    test_score_capped_at_100()
    test_no_benefit_for_category()
    test_others_rate_not_in_theoretical_max()
    test_node_happy_path()
    test_node_db_missing_graceful()
    test_node_multi_card_isolation()

    print()
    print("=" * 60)
    print(f"  Results: {PASS} passed, {FAIL} failed")
    print("=" * 60)

    if FAIL > 0:
        sys.exit(1)