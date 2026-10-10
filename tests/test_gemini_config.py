"""
tests/test_gemini_config.py
─────────────────────────────────────────────────────────────────────────────
A missing GEMINI_API_KEY must surface as a clear error, not a silent
"0 transactions, score 0" result.
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
import time
import unittest.mock as mock

import pytest

from agents import parse_node


def _state() -> dict:
    return {
        "session_id": "cfg",
        "status": "parsing",
        "current_card_idx": 0,
        "cards": [
            {
                "card_id": "axis-airtel",
                "card_name": "Axis Airtel",
                "months": ["2024-01"],
                "pdf_text": "=== STATEMENT: 2024-01 ===\nZOMATO 450.00",
                "transactions": [],
                "total_spend": 0.0,
                "status": "parsing",
            }
        ],
    }


def test_missing_key_returns_error_state():
    with mock.patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
        result = asyncio.run(parse_node.parse_transactions_node(_state()))

    assert result["status"] == "error"
    assert result["ui_action"] == "show_error"
    assert "not configured" in result["error"]


def test_missing_key_is_not_retried():
    with mock.patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
        start = time.monotonic()
        with pytest.raises(parse_node.GeminiNotConfiguredError):
            parse_node._call_gemini("ZOMATO 450")
    # tenacity's backoff waits >= 2s between attempts; no retry means no wait
    assert time.monotonic() - start < 1.5


def test_gemini_unreachable_for_whole_statement_raises():
    # An invalid key, exhausted quota or outage used to come back as "0 purchases"
    with mock.patch.object(parse_node, "_call_gemini", side_effect=RuntimeError("quota")):
        with pytest.raises(parse_node.GeminiUnavailableError):
            parse_node._parse_transactions_from_text("ZOMATO 450", "2024-01")


def test_one_failed_part_keeps_the_rest():
    good = '[{"date": "2024-01-02", "merchant": "SWIGGY", "amount": 300, "category": "food_delivery"}]'
    text = "\n".join(["ZOMATO 450"] * 2000)  # long enough to be sent in several parts
    parts = len(parse_node._chunk_text(text))
    assert parts > 1
    with mock.patch.object(
        parse_node, "_call_gemini", side_effect=[RuntimeError("quota")] + [good] * (parts - 1)
    ):
        txns = parse_node._parse_transactions_from_text(text, "2024-01")
    assert len(txns) == parts - 1
