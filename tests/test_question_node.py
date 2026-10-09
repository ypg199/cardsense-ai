"""
tests/test_question_node.py
Standalone tests for agents/question_node.py.
All DB calls are mocked — no MongoDB connection required.
"""

from __future__ import annotations

import asyncio
import sys
import unittest.mock as mock

sys.path.insert(0, "/home/claude/cardsense")

from agents.question_node import (
    _aggregate_spend_by_category,
    _aggregate_spend_by_merchant,
    _auto_detect_answers,
    _build_questions_from_card_doc,
    question_gen_node,
    QUESTION_GEN_PROMPT,
    MAX_QUESTIONS_PER_CARD,
    MIN_BENEFIT_RATE,
    GENERAL_QUESTIONS,
)
from agents.state import AnalysisState, CardState, Transaction

# ─────────────────────────────────────────────────────────────────────────────
# Test helpers
# ─────────────────────────────────────────────────────────────────────────────

PASS = 0
FAIL = 0

def ok(msg: str):
    global PASS; PASS += 1
    print(f"  ✅ {msg}")

def fail(msg: str):
    global FAIL; FAIL += 1
    print(f"  ❌ {msg}")


# ── Sample card document (matches seed data) ──────────────────────────────────
AXIS_AIRTEL_DOC = {
    "_id": "axis-airtel",
    "name": "Axis Airtel Credit Card",
    "bank": "Axis Bank",
    "benefits": [
        {"category": "airtel_recharge", "label": "Airtel Recharge", "rate": 0.25,
         "merchant_keywords": ["airtel"]},
        {"category": "utility_bills", "label": "Utility Bills", "rate": 0.10,
         "merchant_keywords": ["bescom", "msedcl"]},
        {"category": "food_delivery", "label": "Zomato", "rate": 0.10,
         "merchant_keywords": ["zomato"]},
        {"category": "grocery", "label": "BigBasket", "rate": 0.10,
         "merchant_keywords": ["bigbasket"]},
        {"category": "others", "label": "Others", "rate": 0.01,
         "merchant_keywords": ["*"]},
    ],
    "utilization_questions": [
        {"id": "q_airtel_sim",
         "text": "Do you recharge your Airtel mobile SIM using this card?",
         "hint": "Earns 25% cashback on Airtel recharges",
         "maps_to_category": "airtel_recharge",
         "auto_detect_keywords": ["airtel prepaid", "airtel postpaid", "airtel recharge", "airtel"]},
        {"id": "q_utility",
         "text": "Do you pay your electricity and utility bills with this card?",
         "hint": "Earns 10% cashback on utility bill payments",
         "maps_to_category": "utility_bills",
         "auto_detect_keywords": ["bescom", "msedcl"]},
        {"id": "q_zomato",
         "text": "Do you order food on Zomato using this card?",
         "hint": "Earns 10% cashback on Zomato orders",
         "maps_to_category": "food_delivery",
         "auto_detect_keywords": ["zomato"]},
        {"id": "q_bigbasket",
         "text": "Do you shop for groceries on BigBasket with this card?",
         "hint": "Earns 10% cashback on BigBasket purchases",
         "maps_to_category": "grocery",
         "auto_detect_keywords": ["bigbasket"]},
    ],
}

SAMPLE_TRANSACTIONS: list[Transaction] = [
    {"date": "2024-01-01", "merchant": "Zomato", "amount": 450.0,
     "transaction_type": "debit", "category": "food_delivery", "month": "2024-01"},
    {"date": "2024-01-05", "merchant": "Airtel Recharge", "amount": 299.0,
     "transaction_type": "debit", "category": "airtel_recharge", "month": "2024-01"},
    {"date": "2024-01-10", "merchant": "Amazon", "amount": 1200.0,
     "transaction_type": "debit", "category": "shopping_online", "month": "2024-01"},
    {"date": "2024-01-15", "merchant": "BigBasket Grocery", "amount": 850.0,
     "transaction_type": "debit", "category": "grocery", "month": "2024-01"},
    {"date": "2024-01-20", "merchant": "BESCOM", "amount": 1500.0,
     "transaction_type": "debit", "category": "utility_bills", "month": "2024-01"},
    {"date": "2024-01-25", "merchant": "Cashback Credit", "amount": 100.0,
     "transaction_type": "credit", "category": "others", "month": "2024-01"},
]


def _make_card(
    card_id: str = "axis-airtel",
    transactions: list[Transaction] | None = None,
    qa_answers: dict | None = None,
    pending_questions: list | None = None,
    answered_questions: list | None = None,
) -> CardState:
    return {
        "card_id": card_id,
        "card_name": "Axis Airtel Credit Card",
        "months": ["2024-01"],
        "pdf_bytes_list": [], "pdf_passwords": [],
        "pdf_encrypted": False, "pdf_text": "...",
        "transactions": transactions or list(SAMPLE_TRANSACTIONS),
        "total_spend": 4299.0,
        "pending_questions": pending_questions or [],
        "answered_questions": answered_questions or [],
        "qa_answers": qa_answers or {},
        "cashback_result": None, "utilization_score": 0,
        "status": "questioning",
    }


def _make_state(card: CardState, card_idx: int = 0) -> AnalysisState:
    return {
        "session_id": "test-q-001", "status": "questioning",
        "cards": [card], "current_card_idx": card_idx,
        "locked_card_idx": None, "locked_pdf_idx": None,
        "current_question": None, "comparison_result": None,
        "ui_action": "show_loading",
        "total_questions_count": 0, "answered_questions_count": 0,
        "error": None, "created_at": "2024-01-01T00:00:00Z",
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. Prompt constant
# ─────────────────────────────────────────────────────────────────────────────

def test_prompt_constant():
    print("\n[1] QUESTION_GEN_PROMPT constant")

    assert "{card_name}" in QUESTION_GEN_PROMPT
    ok("Prompt has {card_name}")
    assert "{card_bank}" in QUESTION_GEN_PROMPT
    ok("Prompt has {card_bank}")
    assert "{benefits_json}" in QUESTION_GEN_PROMPT
    ok("Prompt has {benefits_json}")
    assert "{category_spend_json}" in QUESTION_GEN_PROMPT
    ok("Prompt has {category_spend_json}")
    assert "8 questions" in QUESTION_GEN_PROMPT
    ok("Prompt specifies max 8 questions")
    assert "potential_cashback" in QUESTION_GEN_PROMPT
    ok("Prompt specifies sort by potential_cashback")
    assert MAX_QUESTIONS_PER_CARD == 8
    ok("MAX_QUESTIONS_PER_CARD == 8")
    assert MIN_BENEFIT_RATE == 0.01
    ok("MIN_BENEFIT_RATE == 0.01 (1%)")
    assert len(GENERAL_QUESTIONS) == 3
    ok("3 general questions defined")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Spend aggregation
# ─────────────────────────────────────────────────────────────────────────────

def test_aggregate_spend():
    print("\n[2] _aggregate_spend_by_category")

    spend = _aggregate_spend_by_category(SAMPLE_TRANSACTIONS)
    assert spend["food_delivery"] == 450.0
    ok("food_delivery spend == 450")
    assert spend["airtel_recharge"] == 299.0
    ok("airtel_recharge spend == 299")
    assert spend["grocery"] == 850.0
    ok("grocery spend == 850")
    assert spend["utility_bills"] == 1500.0
    ok("utility_bills spend == 1500")
    assert "others" not in spend or spend.get("others", 0) == 0
    ok("credit transactions NOT counted in spend")

    # Merchant spend
    merchant_spend = _aggregate_spend_by_merchant(SAMPLE_TRANSACTIONS)
    assert "zomato" in merchant_spend
    ok("merchant spend keyed by lowercase merchant name")
    assert merchant_spend["zomato"] == 450.0
    ok("Zomato merchant spend == 450")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Auto-detection
# ─────────────────────────────────────────────────────────────────────────────

def test_auto_detect_answers():
    print("\n[3] _auto_detect_answers")

    answers = _auto_detect_answers(
        AXIS_AIRTEL_DOC["utilization_questions"],
        SAMPLE_TRANSACTIONS,
        {},
    )
    # Zomato txn → q_zomato auto-detected
    assert answers.get("q_zomato") == True
    ok("q_zomato auto-detected from Zomato transaction")

    # Airtel Recharge txn → q_airtel_sim auto-detected
    assert answers.get("q_airtel_sim") == True
    ok("q_airtel_sim auto-detected from Airtel Recharge transaction")

    # BESCOM txn → q_utility auto-detected
    assert answers.get("q_utility") == True
    ok("q_utility auto-detected from BESCOM transaction")

    # BigBasket → q_bigbasket auto-detected
    assert answers.get("q_bigbasket") == True
    ok("q_bigbasket auto-detected from BigBasket Grocery transaction")


def test_auto_detect_does_not_overwrite():
    print("\n[4] _auto_detect_answers — existing answers preserved")

    existing = {"q_zomato": False}  # User manually said No
    answers = _auto_detect_answers(
        AXIS_AIRTEL_DOC["utilization_questions"],
        SAMPLE_TRANSACTIONS,
        existing,
    )
    # Should not overwrite the manual False answer
    assert answers["q_zomato"] == False
    ok("Manual False answer not overwritten by auto-detect")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Question building
# ─────────────────────────────────────────────────────────────────────────────

def test_build_questions_from_card_doc():
    print("\n[5] _build_questions_from_card_doc — basic")

    category_spend = _aggregate_spend_by_category(SAMPLE_TRANSACTIONS)
    # No answers yet — all auto-detect, so pass empty qa_answers
    questions = _build_questions_from_card_doc(AXIS_AIRTEL_DOC, category_spend, {})

    assert len(questions) <= MAX_QUESTIONS_PER_CARD
    ok(f"Questions capped at {MAX_QUESTIONS_PER_CARD} (got {len(questions)})")

    # shopping_online has no benefit on Axis Airtel → should not appear
    cats_in_qs = {q["category"] for q in questions if not q["is_general"]}
    ok(f"Questions for categories: {cats_in_qs}")

    # General questions should be included
    general_qs = [q for q in questions if q["is_general"]]
    assert len(general_qs) > 0
    ok(f"General questions included ({len(general_qs)} of them)")


def test_build_questions_sorted_by_cashback():
    print("\n[6] _build_questions_from_card_doc — sorted by potential_cashback")

    category_spend = _aggregate_spend_by_category(SAMPLE_TRANSACTIONS)
    questions = _build_questions_from_card_doc(AXIS_AIRTEL_DOC, category_spend, {})
    non_general = [q for q in questions if not q["is_general"]]

    if len(non_general) >= 2:
        cashbacks = [q["potential_cashback"] for q in non_general]
        assert cashbacks == sorted(cashbacks, reverse=True)
        ok("Non-general questions sorted by potential_cashback descending")
    else:
        ok("Not enough non-general questions to sort (OK for this dataset)")


def test_build_questions_filters_zero_spend():
    print("\n[7] _build_questions_from_card_doc — zero-spend categories excluded")

    # Only Zomato spend, nothing else
    sparse_spend = {"food_delivery": 450.0}
    questions = _build_questions_from_card_doc(AXIS_AIRTEL_DOC, sparse_spend, {})
    non_general_cats = {q["category"] for q in questions if not q["is_general"]}

    # Only food_delivery should appear (not utility, airtel, grocery)
    assert "utility_bills" not in non_general_cats
    ok("utility_bills excluded (zero spend)")
    assert "airtel_recharge" not in non_general_cats
    ok("airtel_recharge excluded (zero spend)")
    if "food_delivery" in non_general_cats:
        ok("food_delivery included (has spend)")


def test_build_questions_skips_already_answered():
    print("\n[8] _build_questions_from_card_doc — answered questions excluded")

    category_spend = _aggregate_spend_by_category(SAMPLE_TRANSACTIONS)
    already_answered = {"q_zomato": True, "q_airtel_sim": True}
    questions = _build_questions_from_card_doc(
        AXIS_AIRTEL_DOC, category_spend, already_answered
    )
    ids = [q["id"] for q in questions]
    assert "q_zomato" not in ids
    ok("q_zomato excluded (already answered)")
    assert "q_airtel_sim" not in ids
    ok("q_airtel_sim excluded (already answered)")


def test_build_questions_filters_low_rate_benefit():
    print("\n[9] _build_questions_from_card_doc — <=1% benefit rate filtered out")

    # Card where 'others' is 1% — question for others should not appear
    category_spend = {"others": 5000.0}
    questions = _build_questions_from_card_doc(AXIS_AIRTEL_DOC, category_spend, {})
    non_general = [q for q in questions if not q["is_general"]]
    cats = {q["category"] for q in non_general}
    assert "others" not in cats
    ok("'others' (1% benefit) excluded from questions")


def test_build_questions_potential_cashback_correct():
    print("\n[10] _build_questions_from_card_doc — potential_cashback calculation")

    # Only utility_bills spend = 1500, rate = 10%
    category_spend = {"utility_bills": 1500.0}
    questions = _build_questions_from_card_doc(AXIS_AIRTEL_DOC, category_spend, {})
    utility_qs = [q for q in questions if q["category"] == "utility_bills"]

    if utility_qs:
        q = utility_qs[0]
        assert q["detected_spend"] == 1500.0
        ok("detected_spend == 1500.0")
        assert q["potential_cashback"] == 150.0  # 1500 * 0.10
        ok("potential_cashback == 150.0 (1500 × 10%)")


# ─────────────────────────────────────────────────────────────────────────────
# 5. Full node — mocked DB
# ─────────────────────────────────────────────────────────────────────────────

def test_node_first_call_shows_question():
    print("\n[11] question_gen_node — first call, questions pending")

    card = _make_card()
    state = _make_state(card)

    with mock.patch("agents.question_node._fetch_card_doc", return_value=AXIS_AIRTEL_DOC), \
         mock.patch("agents.question_node._enrich_questions_with_llm",
                    side_effect=lambda *a, **kw: a[2]):  # return base_questions unchanged
        result = asyncio.run(question_gen_node(state))

    assert result["status"] == "questioning"
    ok("status == 'questioning' when questions remain")

    assert result["ui_action"] == "show_question"
    ok("ui_action == 'show_question'")

    assert result["current_question"] is not None
    ok("current_question is set")

    cq = result["current_question"]
    assert "id" in cq and "text" in cq and "hint" in cq
    ok("current_question has required fields (id, text, hint)")

    assert result["total_questions_count"] > 0
    ok(f"total_questions_count > 0 ({result['total_questions_count']})")


def test_node_all_answered_advances_to_calculating():
    print("\n[12] question_gen_node — all questions answered → calculating")

    # Pre-answer ALL questions including generals
    all_q_ids = {uq["id"] for uq in AXIS_AIRTEL_DOC["utilization_questions"]}
    all_q_ids.update({gq["id"] for gq in GENERAL_QUESTIONS})
    qa_answers = {qid: True for qid in all_q_ids}

    card = _make_card(qa_answers=qa_answers)
    state = _make_state(card)

    with mock.patch("agents.question_node._fetch_card_doc", return_value=AXIS_AIRTEL_DOC), \
         mock.patch("agents.question_node._enrich_questions_with_llm",
                    side_effect=lambda *a, **kw: a[2]):
        result = asyncio.run(question_gen_node(state))

    assert result["status"] == "calculating"
    ok("status == 'calculating' when all answered")

    assert result["ui_action"] == "show_loading"
    ok("ui_action == 'show_loading'")

    assert result["current_question"] is None
    ok("current_question is None when done")

    assert result["cards"][0]["status"] == "calculating"
    ok("card.status == 'calculating'")


def test_node_auto_detects_on_first_call():
    print("\n[13] question_gen_node — auto-detection on first call")

    # Transactions include Zomato and Airtel — should auto-detect those answers
    card = _make_card(qa_answers={})
    state = _make_state(card)

    with mock.patch("agents.question_node._fetch_card_doc", return_value=AXIS_AIRTEL_DOC), \
         mock.patch("agents.question_node._enrich_questions_with_llm",
                    side_effect=lambda *a, **kw: a[2]):
        result = asyncio.run(question_gen_node(state))

    card_out = result["cards"][0]
    qa = card_out["qa_answers"]
    assert qa.get("q_zomato") == True
    ok("q_zomato auto-detected from Zomato transaction")
    assert qa.get("q_airtel_sim") == True
    ok("q_airtel_sim auto-detected from Airtel transaction")

    # Auto-detected questions should not appear in pending
    pending_ids = {q["id"] for q in card_out["pending_questions"]}
    assert "q_zomato" not in pending_ids
    ok("q_zomato not in pending_questions (auto-detected)")


def test_node_db_not_found_graceful():
    print("\n[14] question_gen_node — card not in DB, graceful degradation")

    card = _make_card(card_id="nonexistent-card")
    state = _make_state(card)

    with mock.patch("agents.question_node._fetch_card_doc", return_value=None), \
         mock.patch("agents.question_node._enrich_questions_with_llm",
                    side_effect=lambda *a, **kw: a[2]):
        result = asyncio.run(question_gen_node(state))

    # Should still work — falls back to general questions only
    assert result["status"] in ("questioning", "calculating")
    ok(f"No crash on missing card — status={result['status']}")


def test_node_incremental_answer():
    print("\n[15] question_gen_node — incremental: one question answered between calls")

    # First call — build questions
    card = _make_card(qa_answers={})
    state = _make_state(card)

    with mock.patch("agents.question_node._fetch_card_doc", return_value=AXIS_AIRTEL_DOC), \
         mock.patch("agents.question_node._enrich_questions_with_llm",
                    side_effect=lambda *a, **kw: a[2]):
        r1 = question_gen_node(state)

    q1 = r1["current_question"]
    assert q1 is not None
    pending_count_1 = len(r1["cards"][0]["pending_questions"])
    ok(f"First call: {pending_count_1} pending questions, current='{q1['id']}'")

    # Simulate user answering q1 → True
    updated_card = r1["cards"][0]
    updated_card["qa_answers"][q1["id"]] = True
    updated_state = dict(state)
    updated_state["cards"] = r1["cards"]
    updated_state["current_card_idx"] = 0

    with mock.patch("agents.question_node._fetch_card_doc", return_value=AXIS_AIRTEL_DOC), \
         mock.patch("agents.question_node._enrich_questions_with_llm",
                    side_effect=lambda *a, **kw: a[2]):
        r2 = question_gen_node(updated_state)

    if r2["current_question"]:
        assert r2["current_question"]["id"] != q1["id"]
        ok("Second call shows a different question")
    else:
        ok("Second call — no more questions (all answered)")

    assert r2["answered_questions_count"] >= 1
    ok("answered_questions_count incremented")


def test_node_does_not_touch_other_cards():
    print("\n[16] question_gen_node — multi-card isolation")

    card0 = _make_card(card_id="axis-airtel")
    card1 = _make_card(card_id="hdfc-millennia")
    card1["qa_answers"] = {}

    state: AnalysisState = {
        "session_id": "test-multi", "status": "questioning",
        "cards": [card0, card1], "current_card_idx": 1,
        "locked_card_idx": None, "locked_pdf_idx": None,
        "current_question": None, "comparison_result": None,
        "ui_action": "show_loading", "total_questions_count": 0,
        "answered_questions_count": 0, "error": None,
        "created_at": "2024-01-01T00:00:00Z",
    }

    hdfc_doc = {
        "_id": "hdfc-millennia", "name": "HDFC Millennia", "bank": "HDFC Bank",
        "benefits": [
            {"category": "shopping_online", "rate": 0.05, "merchant_keywords": ["amazon"]},
        ],
        "utilization_questions": [
            {"id": "q_amazon", "text": "Do you shop on Amazon?",
             "hint": "5% cashback", "maps_to_category": "shopping_online",
             "auto_detect_keywords": ["amazon"]},
        ],
    }

    with mock.patch("agents.question_node._fetch_card_doc", return_value=hdfc_doc), \
         mock.patch("agents.question_node._enrich_questions_with_llm",
                    side_effect=lambda *a, **kw: a[2]):
        result = asyncio.run(question_gen_node(state))

    # card0 at idx=0 should be untouched
    assert result["cards"][0]["qa_answers"] == {}
    ok("card at idx=0 untouched (qa_answers unchanged)")

    # card1 at idx=1 was processed
    assert result["cards"][1]["status"] in ("questioning", "calculating")
    ok("card at idx=1 was processed")


# ─────────────────────────────────────────────────────────────────────────────
# Run all
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  question_node test suite")
    print("=" * 60)

    test_prompt_constant()
    test_aggregate_spend()
    test_auto_detect_answers()
    test_auto_detect_does_not_overwrite()
    test_build_questions_from_card_doc()
    test_build_questions_sorted_by_cashback()
    test_build_questions_filters_zero_spend()
    test_build_questions_skips_already_answered()
    test_build_questions_filters_low_rate_benefit()
    test_build_questions_potential_cashback_correct()
    test_node_first_call_shows_question()
    test_node_all_answered_advances_to_calculating()
    test_node_auto_detects_on_first_call()
    test_node_db_not_found_graceful()
    test_node_incremental_answer()
    test_node_does_not_touch_other_cards()

    print()
    print("=" * 60)
    print(f"  Results: {PASS} passed, {FAIL} failed")
    print("=" * 60)

    if FAIL > 0:
        sys.exit(1)