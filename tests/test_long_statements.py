"""
tests/test_long_statements.py
─────────────────────────────────────────────────────────────────────────────
Statements longer than one Gemini request are parsed in parts, and the
benchmark's scoring logic. Gemini is mocked.
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import os
import sys
import unittest.mock as mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents import parse_node
from eval.scoring import score_statement, summarise


def _statement(rows: int) -> str:
    return "\n".join(f"{i % 28 + 1:02d}/03/2026 MERCHANT NUMBER {i:04d} {100 + i}.00 Dr" for i in range(rows))


def test_chunk_text_breaks_between_lines_only():
    text = _statement(400)
    chunks = parse_node._chunk_text(text, limit=2_000)
    assert len(chunks) > 1
    assert all(len(c) <= 2_000 for c in chunks)
    assert "\n".join(chunks).splitlines() == text.splitlines()  # nothing lost or cut


def test_chunk_text_short_text_is_one_part():
    assert parse_node._chunk_text("one line\ntwo lines", limit=2_000) == ["one line\ntwo lines"]


def test_chunk_text_hard_splits_a_single_huge_line():
    chunks = parse_node._chunk_text("x" * 5_000, limit=2_000)
    assert [len(c) for c in chunks] == [2_000, 2_000, 1_000]


def _echo_gemini(chunk: str) -> str:
    """Fake Gemini: one debit per statement line in the part it was given."""
    rows = []
    for line in chunk.splitlines():
        amount = float(line.split()[-2])
        rows.append({"date": "2026-03-01", "merchant": line[11:30], "amount": amount, "category": "others"})
    return json.dumps(rows)


def test_long_statement_keeps_every_transaction():
    text = _statement(600)  # well over PDF_TEXT_CHAR_LIMIT
    assert len(text) > parse_node.PDF_TEXT_CHAR_LIMIT
    with mock.patch.object(parse_node, "_call_gemini", side_effect=_echo_gemini) as gemini:
        txns = parse_node._parse_transactions_from_text(text, "2026-03")
    assert gemini.call_count > 1
    assert len(txns) == 600


def test_failed_part_does_not_discard_the_others():
    text = _statement(600)
    calls = {"n": 0}

    def flaky(chunk):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("quota")
        return _echo_gemini(chunk)

    with mock.patch.object(parse_node, "_call_gemini", side_effect=flaky):
        txns = parse_node._parse_transactions_from_text(text, "2026-03")
    assert 0 < len(txns) < 600


# ── Benchmark scoring ───────────────────────────────────────────────────────

TRUTH = [
    {
        "date": "2026-02-02",
        "description": "SWIGGY",
        "amount": 486.0,
        "transaction_type": "debit",
        "category": "food_delivery",
    },
    {
        "date": "2026-02-05",
        "description": "MYNTRA",
        "amount": 1799.0,
        "transaction_type": "debit",
        "category": "shopping_online",
    },
    {
        "date": "2026-02-09",
        "description": "HPCL",
        "amount": 486.0,
        "transaction_type": "debit",
        "category": "fuel",
    },
]


def test_scoring_perfect_match():
    pred = [{"date": t["date"], "amount": t["amount"], "category": t["category"]} for t in TRUTH]
    s = score_statement("x", TRUTH, pred)
    assert (s.precision, s.recall, s.category_accuracy, s.spend_error) == (1.0, 1.0, 1.0, 0.0)


def test_scoring_prefers_same_date_when_amounts_repeat():
    pred = [
        {"date": "2026-02-09", "amount": 486.0, "category": "fuel"},
        {"date": "2026-02-02", "amount": 486.0, "category": "food_delivery"},
    ]
    s = score_statement("x", TRUTH, pred)
    assert s.matched == 2 and s.date_correct == 2 and s.category_correct == 2
    assert [m["description"] for m in s.misses] == ["MYNTRA"]


def test_scoring_counts_misses_extras_and_wrong_categories():
    pred = [
        {"date": "2026-02-02", "amount": 486.0, "category": "others"},
        {"date": "2026-02-07", "amount": 50.0, "category": "others"},
    ]
    s = score_statement("x", TRUTH, pred)
    assert s.recall == 1 / 3 and s.precision == 1 / 2
    assert len(s.extras) == 1 and len(s.wrong_category) == 1
    total = summarise([s])
    assert total["true_rows"] == 3 and total["category_accuracy"] == 0.0


# ── Malformed Gemini output is retried ──────────────────────────────────────

GOOD = json.dumps([{"date": "2026-03-01", "merchant": "ZOMATO", "amount": 450, "category": "food_delivery"}])


def test_invalid_json_is_retried_once():
    with mock.patch.object(parse_node, "_call_gemini", side_effect=["[{broken", GOOD]) as gemini:
        txns = parse_node._parse_transactions_from_text("01/03 ZOMATO 450", "2026-03")
    assert gemini.call_count == 2
    assert [t["merchant"] for t in txns] == ["ZOMATO"]


def test_off_topic_response_is_retried_then_given_up():
    with mock.patch.object(parse_node, "_call_gemini", return_value='{"note": "unrelated"}') as gemini:
        txns = parse_node._parse_transactions_from_text("01/03 ZOMATO 450", "2026-03")
    assert gemini.call_count == parse_node.JSON_ATTEMPTS
    assert txns == []


def test_parser_requests_json_mode():
    fake = mock.MagicMock()
    with (
        mock.patch.dict("os.environ", {"GEMINI_API_KEY": "k"}),
        mock.patch.dict(
            "sys.modules", {"langchain_google_genai": mock.MagicMock(ChatGoogleGenerativeAI=fake)}
        ),
    ):
        parse_node._get_llm()
    assert fake.call_args.kwargs["response_mime_type"] == "application/json"
