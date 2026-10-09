"""POST /session/sample: the built-in sample statements."""

from __future__ import annotations

import asyncio
import unittest.mock as mock

from agents.spend_summary import summarise_spend
from api.routes import session as routes
from tests.test_api import _make_client, _stop_patches


def test_sample_data_covers_four_months_of_one_card():
    sample = routes._load_sample()
    assert sample["card_id"] == "hdfc-millennia"
    assert [m["month"] for m in sample["months"]] == ["2026-01", "2026-02", "2026-03", "2026-04"]
    for m in sample["months"]:
        assert m["transactions"], m["month"]
        assert all(t["month"] == m["month"] for t in m["transactions"])
    cards = [
        {
            "card_id": "s",
            "card_name": "S",
            "transactions": [t for m in sample["months"] for t in m["transactions"]],
        }
    ]
    assert summarise_spend(cards)["months"] == ["2026-01", "2026-02", "2026-03", "2026-04"]


def test_spend_mode_goes_straight_to_the_analyser():
    client, patches = _make_client()
    try:
        r = client.post("/session/sample", json={"mode": "spend"})
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["ui_action"] == "show_analyser"
        assert data["sample"] is True and data["mode"] == "spend"
        card = data["cards"][0]
        assert card["months"] == ["2026-01", "2026-02", "2026-03", "2026-04"]
        assert card["transactions_count"] > 50 and card["total_spend"] > 0
        routes._run_graph.assert_not_called()
    finally:
        _stop_patches(patches)

    state = {
        "session_id": "s",
        "sample": True,
        "cards": [{"card_id": "c", "card_name": "C", "transactions": []}],
    }
    client, patches = _make_client(load_session_return=state)
    try:
        assert client.get("/session/s/spend").json()["sample"] is True
    finally:
        _stop_patches(patches)


def test_full_mode_skips_parsing_and_starts_the_quiz():
    client, patches = _make_client(run_graph_return={})
    try:
        r = client.post("/session/sample")
        assert r.status_code == 201, r.text
        state = routes._run_graph.call_args.args[0]
        assert state["status"] == "questioning"
        assert state["sample"] is True
        assert state["cards"][0]["transactions"]
        assert state["cards"][0]["pdf_bytes_list"] == []
    finally:
        _stop_patches(patches)


def test_unknown_mode_is_rejected():
    client, patches = _make_client()
    try:
        assert client.post("/session/sample", json={"mode": "hack"}).status_code == 422
    finally:
        _stop_patches(patches)


def test_sample_produces_quiz_questions_without_an_api_key(monkeypatch):
    """The rule-based quiz works on the sample data with no Gemini key."""
    from agents.question_node import question_gen_node
    from db.seed import SEED_CARDS

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    sample = routes._load_sample()
    txns = [t for m in sample["months"] for t in m["transactions"]]
    state = {
        "session_id": "s",
        "status": "questioning",
        "current_card_idx": 0,
        "answered_questions_count": 0,
        "total_questions_count": 0,
        "cards": [
            {
                "card_id": "hdfc-millennia",
                "card_name": "HDFC Millennia",
                "months": [m["month"] for m in sample["months"]],
                "transactions": txns,
                "total_spend": sum(t["amount"] for t in txns if t["transaction_type"] == "debit"),
                "pending_questions": [],
                "answered_questions": [],
                "qa_answers": {},
                "status": "questioning",
            }
        ],
    }
    doc = next(c for c in SEED_CARDS if c["_id"] == "hdfc-millennia")
    with mock.patch("agents.question_node._fetch_card_doc", mock.AsyncMock(return_value=doc)):
        out = asyncio.run(question_gen_node(state))
    assert out["ui_action"] == "show_question"
    assert out["current_question"]["text"]
