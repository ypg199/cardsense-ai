"""
tests/test_parse_node.py
Standalone tests for agents/parse_node.py.
All Gemini calls are mocked — no API key required.
"""

from __future__ import annotations

import json
import sys
import unittest.mock as mock

sys.path.insert(0, "/home/claude/cardsense")

# ── patch Gemini before any import of parse_node ─────────────────────────────
MOCK_TRANSACTIONS = [
    {"date": "2024-01-01", "merchant": "Zomato", "amount": 450.0,
     "transaction_type": "debit", "category": "food_delivery"},
    {"date": "2024-01-05", "merchant": "Airtel Recharge", "amount": 299.0,
     "transaction_type": "debit", "category": "airtel_recharge"},
    {"date": "2024-01-10", "merchant": "Amazon", "amount": 1200.0,
     "transaction_type": "debit", "category": "shopping_online"},
    {"date": "2024-01-15", "merchant": "BigBasket", "amount": 850.0,
     "transaction_type": "debit", "category": "grocery"},
    {"date": "2024-01-20", "merchant": "BESCOM", "amount": 1500.0,
     "transaction_type": "debit", "category": "utility_bills"},
    {"date": "2024-01-25", "merchant": "Cashback Credit", "amount": 100.0,
     "transaction_type": "credit", "category": "others"},
]

from agents.parse_node import (
    _clean_gemini_json,
    _normalise_transaction,
    _split_by_month,
    _parse_transactions_from_text,
    parse_transactions_node,
    TRANSACTION_PARSE_PROMPT,
    VALID_CATEGORIES,
    PDF_TEXT_CHAR_LIMIT,
)
from agents.state import AnalysisState, CardState


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


def _make_card(pdf_text: str = "", months: list[str] | None = None) -> CardState:
    return {
        "card_id": "axis-airtel", "card_name": "Axis Airtel",
        "months": months or ["2024-01"],
        "pdf_bytes_list": [], "pdf_passwords": [],
        "pdf_encrypted": False, "pdf_text": pdf_text,
        "transactions": [], "total_spend": 0.0,
        "pending_questions": [], "answered_questions": [],
        "qa_answers": {}, "cashback_result": None,
        "utilization_score": 0, "status": "parsing",
    }


def _make_state(card: CardState, card_idx: int = 0) -> AnalysisState:
    return {
        "session_id": "test-parse-001", "status": "parsing",
        "cards": [card], "current_card_idx": card_idx,
        "locked_card_idx": None, "locked_pdf_idx": None,
        "current_question": None, "comparison_result": None,
        "ui_action": "show_loading", "total_questions_count": 0,
        "answered_questions_count": 0, "error": None,
        "created_at": "2024-01-01T00:00:00Z",
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. Prompt constant checks
# ─────────────────────────────────────────────────────────────────────────────

def test_prompt_constants():
    print("\n[1] Prompt and constant checks")

    # Prompt contains key spec phrases
    assert "{pdf_text}" in TRANSACTION_PARSE_PROMPT
    ok("TRANSACTION_PARSE_PROMPT contains {pdf_text} placeholder")

    assert "YYYY-MM-DD" in TRANSACTION_PARSE_PROMPT
    ok("Prompt specifies YYYY-MM-DD date format")

    for kw in ["zomato", "airtel", "amazon", "flipkart", "bigbasket", "emi"]:
        assert kw in TRANSACTION_PARSE_PROMPT.lower()
    ok("All auto-rule keywords present in prompt")

    assert "No markdown" in TRANSACTION_PARSE_PROMPT
    ok("Prompt says 'No markdown'")

    assert PDF_TEXT_CHAR_LIMIT == 10_000
    ok("PDF_TEXT_CHAR_LIMIT == 10 000 (spec requirement)")

    assert len(VALID_CATEGORIES) == 16
    ok(f"VALID_CATEGORIES has all 16 categories")

    for cat in ["airtel_recharge", "food_delivery", "emi", "fuel", "others"]:
        assert cat in VALID_CATEGORIES
    ok("Spot-checked categories present")


# ─────────────────────────────────────────────────────────────────────────────
# 2. JSON cleaner
# ─────────────────────────────────────────────────────────────────────────────

def test_clean_gemini_json():
    print("\n[2] _clean_gemini_json — markdown fence stripping")

    cases = [
        # (input, should_contain)
        ('```json\n[{"a":1}]\n```',        '[{"a":1}]'),
        ('```\n[{"a":1}]\n```',            '[{"a":1}]'),
        ('[{"a":1}]',                      '[{"a":1}]'),
        ('Here is the result:\n[{"a":1}]\nDone.', '[{"a":1}]'),
    ]
    for raw, expected_fragment in cases:
        result = _clean_gemini_json(raw)
        assert expected_fragment in result, f"Expected '{expected_fragment}' in '{result}'"
    ok("Strips ```json fences")
    ok("Strips bare ``` fences")
    ok("Passes through plain JSON unchanged")
    ok("Extracts JSON array from surrounding prose")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Transaction normalisation
# ─────────────────────────────────────────────────────────────────────────────

def test_normalise_transaction():
    print("\n[3] _normalise_transaction — coercion and validation")

    # Happy path
    t = _normalise_transaction(
        {"date": "2024-01-05", "merchant": "Zomato", "amount": 450.0,
         "transaction_type": "debit", "category": "food_delivery"},
        "2024-01"
    )
    assert t is not None
    assert t["date"] == "2024-01-05"
    assert t["merchant"] == "Zomato"
    assert t["amount"] == 450.0
    assert t["transaction_type"] == "debit"
    assert t["category"] == "food_delivery"
    assert t["month"] == "2024-01"
    ok("Valid transaction normalised correctly")

    # Unknown category → 'others'
    t2 = _normalise_transaction(
        {"date": "2024-01-01", "merchant": "X", "amount": 100.0,
         "transaction_type": "debit", "category": "INVALID_CAT"},
        "2024-01"
    )
    assert t2["category"] == "others"
    ok("Unknown category coerced to 'others'")

    # Unknown transaction_type → 'debit'
    t3 = _normalise_transaction(
        {"date": "2024-01-01", "merchant": "Y", "amount": 50.0,
         "transaction_type": "purchase", "category": "grocery"},
        "2024-01"
    )
    assert t3["transaction_type"] == "debit"
    ok("Unknown transaction_type coerced to 'debit'")

    # Negative amount → made positive
    t4 = _normalise_transaction(
        {"date": "2024-01-10", "merchant": "Z", "amount": -300.0,
         "transaction_type": "debit", "category": "fuel"},
        "2024-01"
    )
    assert t4["amount"] == 300.0
    ok("Negative amount made positive (abs)")

    # Bad date format — doesn't crash, gets placeholder date
    t5 = _normalise_transaction(
        {"date": "01/05/2024", "merchant": "W", "amount": 200.0,
         "transaction_type": "debit", "category": "others"},
        "2024-01"
    )
    assert t5 is not None
    ok("Bad date format doesn't crash (returns placeholder)")

    # Month inferred from date
    t6 = _normalise_transaction(
        {"date": "2024-03-15", "merchant": "Amazon", "amount": 500.0,
         "transaction_type": "debit", "category": "shopping_online"},
        "2024-01"
    )
    assert t6["month"] == "2024-03"  # from date, not from fallback
    ok("Month inferred from date field when valid")

    # Missing merchant → 'Unknown'
    t7 = _normalise_transaction(
        {"date": "2024-01-01", "amount": 100.0,
         "transaction_type": "debit", "category": "others"},
        "2024-01"
    )
    assert t7["merchant"] == "Unknown"
    ok("Missing merchant defaulted to 'Unknown'")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Month splitter
# ─────────────────────────────────────────────────────────────────────────────

def test_split_by_month():
    print("\n[4] _split_by_month — multi-month text splitting")

    # Multi-month text produced by pdf_node
    text = (
        "=== STATEMENT: 2024-01 ===\nZomato 450\nAirtel 299\n\n"
        "=== STATEMENT: 2024-02 ===\nAmazon 1200\nBigBasket 850\n"
    )
    chunks = _split_by_month(text, ["2024-01", "2024-02"])
    assert len(chunks) == 2
    ok("Two month chunks found")

    labels = [c[0] for c in chunks]
    assert "2024-01" in labels and "2024-02" in labels
    ok("Month labels correctly extracted")

    jan_text = next(t for l, t in chunks if l == "2024-01")
    assert "Zomato" in jan_text or "airtel" in jan_text.lower() or "Airtel" in jan_text
    ok("January chunk contains January transactions")

    feb_text = next(t for l, t in chunks if l == "2024-02")
    assert "Amazon" in feb_text or "BigBasket" in feb_text
    ok("February chunk contains February transactions")

    # Single month — no separator
    single = _split_by_month("STATEMENT TEXT\nZomato 450", ["2024-01"])
    assert len(single) == 1
    assert single[0][0] == "2024-01"
    ok("Single month (no separator) falls back to months[0]")


# ─────────────────────────────────────────────────────────────────────────────
# 5. _parse_transactions_from_text with mocked Gemini
# ─────────────────────────────────────────────────────────────────────────────

def test_parse_transactions_from_text_success():
    print("\n[5] _parse_transactions_from_text — mocked Gemini success")

    mock_json = json.dumps(MOCK_TRANSACTIONS)

    with mock.patch("agents.parse_node._call_gemini", return_value=mock_json):
        txns = _parse_transactions_from_text("some statement text", "2024-01")

    assert len(txns) == 6
    ok(f"Parsed {len(txns)} transactions from mock response")

    debit_txns = [t for t in txns if t["transaction_type"] == "debit"]
    assert len(debit_txns) == 5
    ok("5 debit + 1 credit correctly parsed")

    categories = {t["category"] for t in txns}
    assert "food_delivery" in categories
    assert "airtel_recharge" in categories
    ok("Category assignment preserved")

    for t in txns:
        assert t["month"] in ("2024-01",)
    ok("Month label attached to all transactions")


def test_parse_transactions_from_text_fenced_json():
    print("\n[6] _parse_transactions_from_text — Gemini wraps in markdown fences")

    fenced = "```json\n" + json.dumps(MOCK_TRANSACTIONS[:3]) + "\n```"
    with mock.patch("agents.parse_node._call_gemini", return_value=fenced):
        txns = _parse_transactions_from_text("text", "2024-02")

    assert len(txns) == 3
    ok("Markdown-fenced JSON correctly parsed")


def test_parse_transactions_empty_pdf_text():
    print("\n[7] _parse_transactions_from_text — empty pdf_text")

    with mock.patch("agents.parse_node._call_gemini") as m:
        txns = _parse_transactions_from_text("", "2024-01")
        m.assert_not_called()

    assert txns == []
    ok("Empty pdf_text skips Gemini call, returns []")


def test_parse_transactions_gemini_failure():
    print("\n[8] _parse_transactions_from_text — Gemini raises exception")

    with mock.patch("agents.parse_node._call_gemini", side_effect=Exception("API Error")):
        txns = _parse_transactions_from_text("some text", "2024-01")

    assert txns == []
    ok("Gemini failure returns empty list (no crash)")


def test_parse_transactions_bad_json():
    print("\n[9] _parse_transactions_from_text — Gemini returns invalid JSON")

    with mock.patch("agents.parse_node._call_gemini", return_value="not json at all"):
        txns = _parse_transactions_from_text("some text", "2024-01")

    assert txns == []
    ok("Invalid JSON returns empty list (no crash)")


def test_parse_transactions_partial_bad_rows():
    print("\n[10] _parse_transactions_from_text — some rows malformed")

    mixed = [
        {"date": "2024-01-01", "merchant": "Good", "amount": 100.0,
         "transaction_type": "debit", "category": "grocery"},
        "this is not a dict",
        {"date": "2024-01-02", "merchant": "Also Good", "amount": 200.0,
         "transaction_type": "debit", "category": "fuel"},
    ]
    with mock.patch("agents.parse_node._call_gemini", return_value=json.dumps(mixed)):
        txns = _parse_transactions_from_text("text", "2024-01")

    # Non-dict entries skipped, valid ones kept
    assert len(txns) == 2
    ok("Non-dict rows skipped, valid rows kept")


# ─────────────────────────────────────────────────────────────────────────────
# 6. Full node tests
# ─────────────────────────────────────────────────────────────────────────────

def test_node_happy_path():
    print("\n[11] parse_transactions_node — full node, mocked Gemini")

    pdf_text = "=== STATEMENT: 2024-01 ===\nZomato 450\nAirtel 299"
    card = _make_card(pdf_text=pdf_text, months=["2024-01"])
    state = _make_state(card)

    mock_response = json.dumps([
        {"date": "2024-01-01", "merchant": "Zomato", "amount": 450.0,
         "transaction_type": "debit", "category": "food_delivery"},
        {"date": "2024-01-05", "merchant": "Airtel Recharge", "amount": 299.0,
         "transaction_type": "debit", "category": "airtel_recharge"},
    ])

    with mock.patch("agents.parse_node._call_gemini", return_value=mock_response):
        result = parse_transactions_node(state)

    assert result["status"] == "questioning"
    ok("status == 'questioning' after parsing")

    assert result["ui_action"] == "show_loading"
    ok("ui_action == 'show_loading'")

    assert result["error"] is None
    ok("error is None")

    card_out = result["cards"][0]
    assert card_out["status"] == "questioning"
    ok("card.status == 'questioning'")

    assert len(card_out["transactions"]) == 2
    ok(f"2 transactions stored in card state")

    assert card_out["total_spend"] == 749.0
    ok(f"total_spend == 749.0 (sum of debits)")


def test_node_multi_month():
    print("\n[12] parse_transactions_node — multi-month (two Gemini calls)")

    pdf_text = (
        "=== STATEMENT: 2024-01 ===\nZomato 450\n\n"
        "=== STATEMENT: 2024-02 ===\nAmazon 1200\n"
    )
    card = _make_card(pdf_text=pdf_text, months=["2024-01", "2024-02"])
    state = _make_state(card)

    call_count = {"n": 0}
    responses = [
        json.dumps([{"date": "2024-01-01", "merchant": "Zomato", "amount": 450.0,
                     "transaction_type": "debit", "category": "food_delivery"}]),
        json.dumps([{"date": "2024-02-10", "merchant": "Amazon", "amount": 1200.0,
                     "transaction_type": "debit", "category": "shopping_online"}]),
    ]

    def mock_gemini(text):
        idx = call_count["n"]
        call_count["n"] += 1
        return responses[idx] if idx < len(responses) else "[]"

    with mock.patch("agents.parse_node._call_gemini", side_effect=mock_gemini):
        result = parse_transactions_node(state)

    assert call_count["n"] == 2
    ok("Gemini called once per month (2 calls)")

    txns = result["cards"][0]["transactions"]
    assert len(txns) == 2
    ok("Transactions from both months combined")

    months_seen = {t["month"] for t in txns}
    assert "2024-01" in months_seen and "2024-02" in months_seen
    ok("Both month labels present in transactions")

    total = result["cards"][0]["total_spend"]
    assert total == 1650.0
    ok(f"total_spend == 1650.0 (sum across both months)")


def test_node_empty_pdf_text():
    print("\n[13] parse_transactions_node — empty pdf_text")

    card = _make_card(pdf_text="", months=["2024-01"])
    state = _make_state(card)

    with mock.patch("agents.parse_node._call_gemini") as m:
        result = parse_transactions_node(state)
        m.assert_not_called()

    assert result["status"] == "questioning"
    ok("Node still returns 'questioning' with empty text (graceful)")

    assert result["cards"][0]["transactions"] == []
    ok("transactions == [] for empty pdf_text")

    assert result["cards"][0]["total_spend"] == 0.0
    ok("total_spend == 0.0")


def test_node_credits_excluded_from_total():
    print("\n[14] parse_transactions_node — credits not counted in total_spend")

    card = _make_card(pdf_text="some text", months=["2024-01"])
    state = _make_state(card)

    mixed = json.dumps([
        {"date": "2024-01-01", "merchant": "Purchase", "amount": 1000.0,
         "transaction_type": "debit", "category": "shopping_online"},
        {"date": "2024-01-02", "merchant": "Cashback", "amount": 50.0,
         "transaction_type": "credit", "category": "others"},
        {"date": "2024-01-03", "merchant": "Refund", "amount": 200.0,
         "transaction_type": "refund", "category": "others"},
    ])

    with mock.patch("agents.parse_node._call_gemini", return_value=mixed):
        result = parse_transactions_node(state)

    assert result["cards"][0]["total_spend"] == 1000.0
    ok("Only debit transactions counted in total_spend")

    assert len(result["cards"][0]["transactions"]) == 3
    ok("All 3 transaction rows stored (incl. credit/refund)")


def test_node_does_not_touch_other_cards():
    print("\n[15] parse_transactions_node — multi-card, only active card modified")

    card0 = _make_card(pdf_text="card 0 text", months=["2024-01"])
    card1 = _make_card(pdf_text="card 1 text", months=["2024-01"])
    card1["card_id"] = "hdfc-millennia"

    state: AnalysisState = {
        "session_id": "test-multi", "status": "parsing",
        "cards": [card0, card1], "current_card_idx": 1,
        "locked_card_idx": None, "locked_pdf_idx": None,
        "current_question": None, "comparison_result": None,
        "ui_action": "show_loading", "total_questions_count": 0,
        "answered_questions_count": 0, "error": None,
        "created_at": "2024-01-01T00:00:00Z",
    }

    mock_response = json.dumps([
        {"date": "2024-01-01", "merchant": "Swiggy", "amount": 350.0,
         "transaction_type": "debit", "category": "food_delivery"},
    ])

    with mock.patch("agents.parse_node._call_gemini", return_value=mock_response):
        result = parse_transactions_node(state)

    # card at idx=1 should have transactions
    assert len(result["cards"][1]["transactions"]) == 1
    ok("Active card (idx=1) has transactions")

    # card at idx=0 should be untouched
    assert result["cards"][0]["transactions"] == []
    ok("Inactive card (idx=0) untouched")


# ─────────────────────────────────────────────────────────────────────────────
# Run all
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  parse_node test suite")
    print("=" * 60)

    test_prompt_constants()
    test_clean_gemini_json()
    test_normalise_transaction()
    test_split_by_month()
    test_parse_transactions_from_text_success()
    test_parse_transactions_from_text_fenced_json()
    test_parse_transactions_empty_pdf_text()
    test_parse_transactions_gemini_failure()
    test_parse_transactions_bad_json()
    test_parse_transactions_partial_bad_rows()
    test_node_happy_path()
    test_node_multi_month()
    test_node_empty_pdf_text()
    test_node_credits_excluded_from_total()
    test_node_does_not_touch_other_cards()

    print()
    print("=" * 60)
    print(f"  Results: {PASS} passed, {FAIL} failed")
    print("=" * 60)

    if FAIL > 0:
        sys.exit(1)
