"""
tests/test_fee_tables.py
─────────────────────────────────────────────────────────────────────────────
SBI statements end with a "Schedule of Charges" table listing every SBI card
with its annual and renewal fee. Gemini returned those rows as purchases with
a made-up date, so the Spend Analyser showed "Biggest purchase: ₹9,999 at
AURUM", card names as top merchants and a bogus month. Rows whose amount isn't
on a dated statement line are now dropped. Gemini is mocked; the text comes
from a real PDF run through the same extractor as uploads.
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import os
import sys
import unittest.mock as mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.parse_node import _drop_rows_without_a_dated_line, _parse_transactions_from_text
from agents.pdf_node import _extract_text
from eval.make_statements import sbi

PURCHASES = [
    {
        "date": "2026-08-03",
        "description": "MMT*MAKEMYTRIP FLIGHTS",
        "amount": 2470.0,
        "transaction_type": "debit",
    },
    {"date": "2026-08-09", "description": "BOOKMYSHOW MUMBAI", "amount": 715.0, "transaction_type": "debit"},
    {"date": "2026-08-14", "description": "BBNOW BANGALORE", "amount": 345.5, "transaction_type": "debit"},
    {
        "date": "2026-08-20",
        "description": "PAYMENT RECEIVED - THANK YOU",
        "amount": 5000.0,
        "transaction_type": "credit",
    },
]

FEE_SCHEDULE = [
    ("AURUM", "9,999", "9,999 (Waived off on annual spends of 12 Lakh or more"),
    ("KrisFlyer SBI Card Apex", "9,999", "9,999"),
    ("SBI Card PRIME", "2,999", "2,999 (Waived off on annual spends of 3 Lakh or more"),
    ("Doctor's SBI Card", "1,499", "1,499 (Waived off on annual spends of 2 Lakh or more"),
    ("Shaurya SBI Card", "250", "250 (Waived off on annual spends of 50,000 or more"),
    ("SBI Card Unnati", "NIL", "499 (5th Year Onwards)"),
    ("Air India SBI Signature Card", "4,999", "4,999"),
    ("Nature's Basket SBI Card", "1,499", "1,499 (Waived off on annual spends of 2 Lakh or more"),
]


def _statement_text() -> str:
    w = sbi("SimplyCLICK", PURCHASES, "01 Aug 26 to 31 Aug 26")
    w.y = 800  # the schedule of charges starts on its own page
    w.row([(40, "Schedule of Charges")])
    w.row([(40, "Credit Card Name"), (300, "Annual Fee (Rs.)"), (380, "Renewal Fee (Rs.)")])
    for name, annual, renewal in FEE_SCHEDULE:
        w.row([(40, name), (300, annual), (380, renewal)])
        w.row([(380, "in the preceding year)")] if "Waived" in renewal else [])
    return _extract_text(w.doc.tobytes(), "2026-08")


def _row(date: str, merchant: str, amount: float, txn_type: str = "debit") -> dict:
    return {
        "date": date,
        "merchant": merchant,
        "amount": amount,
        "transaction_type": txn_type,
        "category": "others",
    }


# What Gemini returned on the live site: the real rows plus the fee table,
# every fee row stamped with the same invented date.
GEMINI_REPLY = [
    _row("2026-08-03", "MakeMyTrip", 2470.0),
    _row("2026-08-09", "BookMyShow", 715.0),
    _row("2026-08-14", "BBNow", 345.5),
    _row("2026-08-20", "Payment received", 5000.0, "credit"),
    _row("2024-05-22", "AURUM", 9999.0),
    _row("2024-05-22", "KrisFlyer SBI Card Apex", 9999.0),
    _row("2024-05-22", "SBI Card PRIME", 2999.0),
    _row("2024-05-22", "Doctor's SBI Card", 1499.0),
    _row("2024-05-22", "Shaurya SBI Card", 250.0),
    _row("2024-06-01", "SBI Card Unnati", 499.0),
    _row("2024-05-22", "Air India SBI Signature Card", 4999.0),
    _row("2024-05-22", "Nature's Basket SBI Card", 1499.0),
]


def test_fee_schedule_rows_are_not_spending():
    text = _statement_text()
    assert "Schedule of Charges" in text

    with mock.patch("agents.parse_node._call_gemini", return_value=json.dumps(GEMINI_REPLY)):
        txns = _parse_transactions_from_text(text, "2026-08")

    assert [t["merchant"] for t in txns] == ["MakeMyTrip", "BookMyShow", "BBNow", "Payment received"]
    assert {t["month"] for t in txns} == {"2026-08"}  # no bogus May/Jun '24 months
    assert sum(t["amount"] for t in txns if t["transaction_type"] == "debit") == 3530.5


def test_amount_formats_on_dated_lines_are_kept():
    text = "\n".join(
        [
            "05/08/2026 SWIGGY BANGALORE 1,234.50 Dr",
            "06-Aug-2026 AMAZON PAY Rs.12,000 Dr",
            "07 Aug 26 IRCTC E-TICKETING NEW",
            "DELHI 845.00 D",  # wrapped row: the amount sits below its date
            "Aug 08, 2026 ZOMATO 99.9",
        ]
    )
    rows = [
        _row("", m, a)
        for m, a in [("Swiggy", 1234.5), ("Amazon", 12000.0), ("IRCTC", 845.0), ("Zomato", 99.9)]
    ]
    assert _drop_rows_without_a_dated_line(rows, text) == rows


def test_unrecognised_layout_is_left_alone():
    rows = [_row("2026-08-01", "Swiggy", 250.0)]
    # No dated lines at all: not a layout we can check, so nothing is dropped
    assert _drop_rows_without_a_dated_line(rows, "SWIGGY 250.00") == rows
    # Every row unmatched: keep them rather than return an empty statement
    assert _drop_rows_without_a_dated_line(rows, "05/08/2026 something 999.00") == rows
