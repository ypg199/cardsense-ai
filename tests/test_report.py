"""agents/report.py and GET /session/{id}/report.pdf."""

from __future__ import annotations

import fitz

from agents.report import build_report
from api.routes import session as routes
from tests.test_api import _make_client, _stop_patches


def _sample_cards() -> list[dict]:
    sample = routes._load_sample()
    return [
        {
            "card_id": "hdfc-millennia",
            "card_name": "HDFC Millennia Credit Card",
            "transactions": [t for m in sample["months"] for t in m["transactions"]],
        }
    ]


def _full_state() -> dict:
    cards = _sample_cards()
    cards[0]["cashback_result"] = {
        "earned_breakdown": {"food_delivery": 1640.0, "shopping_online": 1412.0},
        "missed_breakdown": {"travel_flights": 300.0},
    }
    return {
        "session_id": "s",
        "sample": True,
        "cards": cards,
        "comparison_result": {
            "verdict": "Switch recommended",
            "verdict_reason": "Axis Airtel Credit Card would earn about 863 more a month.",
            "card_score": 82,
            "recommendations": [
                {
                    "card_name": "Axis Airtel Credit Card",
                    "improvement_over_current_monthly": 863,
                    "why_better": "Higher rate on utility bills.",
                    "annual_fee": 500,
                }
            ],
            "tips": ["Set up auto-pay for utility bills."],
        },
    }


def _text(pdf: bytes) -> str:
    with fitz.open(stream=pdf, filetype="pdf") as doc:
        return "\n".join(page.get_text() for page in doc)


def test_full_report_has_verdict_and_cards():
    pdf = build_report(_full_state())
    assert pdf.startswith(b"%PDF")
    text = _text(pdf)
    assert "Credit card report" in text
    assert "Switch recommended" in text
    assert "HDFC Millennia Credit Card" in text
    assert "Axis Airtel Credit Card" in text
    assert "sample statements" in text


def test_spend_only_report_skips_the_verdict():
    state = {"session_id": "s", "mode": "spend", "cards": _sample_cards()}
    text = _text(build_report(state))
    assert "Spending report" in text
    assert "Switch recommended" not in text
    assert "Top merchants" in text


def test_route_returns_a_pdf_named_after_the_last_month():
    client, patches = _make_client(load_session_return=_full_state())
    try:
        r = client.get("/session/s/report.pdf")
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "application/pdf"
        assert 'filename="cardsense-report-2026-04.pdf"' in r.headers["content-disposition"]
        assert r.content.startswith(b"%PDF")
    finally:
        _stop_patches(patches)


def test_route_404_for_unknown_session():
    client, patches = _make_client(load_session_return=None)
    try:
        assert client.get("/session/nope/report.pdf").status_code == 404
    finally:
        _stop_patches(patches)


def test_route_409_before_any_statement_is_read():
    state = {"session_id": "s", "cards": [{"card_id": "c", "card_name": "C", "transactions": []}]}
    client, patches = _make_client(load_session_return=state)
    try:
        assert client.get("/session/s/report.pdf").status_code == 409
    finally:
        _stop_patches(patches)
