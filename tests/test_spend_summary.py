"""Spend Analyser aggregates and the GET /session/{id}/spend route."""

from __future__ import annotations

import pytest

from agents.spend_summary import summarise_spend
from tests.test_api import MOCK_SESSION_ID, _make_client, _stop_patches


def _txn(date, merchant, amount, category, kind="debit", month=None):
    return {
        "date": date,
        "merchant": merchant,
        "amount": amount,
        "transaction_type": kind,
        "category": category,
        "month": month or date[:7],
    }


CARDS = [
    {
        "card_id": "hdfc-millennia",
        "card_name": "HDFC Millennia",
        "transactions": [
            _txn("2024-01-05", "Swiggy", 450.0, "food_delivery"),
            _txn("2024-01-09", "SWIGGY", 550.0, "food_delivery"),
            _txn("2024-01-12", "Amazon", 2000.0, "online_shopping"),
            _txn("2024-01-20", "Payment received", 5000.0, "others", kind="credit"),
            _txn("2024-02-03", "Amazon", 500.0, "online_shopping", kind="refund"),
            _txn("2024-02-04", "Indian Oil", 1500.0, "fuel"),
        ],
    },
    {
        "card_id": "axis-airtel",
        "card_name": "Axis Airtel",
        "transactions": [
            _txn("2024-02-10", "Airtel", 799.0, "utility_bills"),
            _txn("bad-date", "BigBasket", 1200.0, "grocery", month="2024-03"),
        ],
    },
]


def test_monthly_totals_net_refunds_and_skip_credits():
    s = summarise_spend(CARDS)
    by_month = {m["month"]: m for m in s["monthly"]}
    assert s["months"] == ["2024-01", "2024-02", "2024-03"]
    assert by_month["2024-01"]["total"] == 3000.0  # the bill payment credit is ignored
    assert by_month["2024-02"]["total"] == pytest.approx(1500 + 799 - 500)
    assert by_month["2024-03"]["total"] == 1200.0  # falls back to the statement month label
    assert by_month["2024-01"]["count"] == 3
    assert s["refunds"] == 500.0
    assert s["transactions"] == 6
    assert s["total_spend"] == pytest.approx(3000 + 1799 + 1200)


def test_categories_months_and_cards_breakdown():
    s = summarise_spend(CARDS)
    cats = {c["category"]: c for c in s["categories"]}
    assert s["categories"][0]["category"] == "online_shopping"  # 2000 - 500 refund = 1500, ties fuel
    assert cats["online_shopping"]["total"] == 1500.0
    assert cats["food_delivery"]["count"] == 2
    assert sum(c["share"] for c in s["categories"]) == pytest.approx(1.0, abs=1e-3)
    feb = next(m for m in s["monthly"] if m["month"] == "2024-02")
    assert feb["by_card"] == {"hdfc-millennia": 1000.0, "axis-airtel": 799.0}
    assert "online_shopping" not in feb["by_category"]  # a refund-only month shows no negative bar


def test_merchants_are_grouped_case_insensitively_and_largest_sorted():
    s = summarise_spend(CARDS)
    swiggy = next(m for m in s["merchants"] if m["merchant"].upper() == "SWIGGY")
    assert swiggy["total"] == 1000.0 and swiggy["count"] == 2
    amounts = [t["amount"] for t in s["largest"]]
    assert amounts == sorted(amounts, reverse=True)
    assert s["largest"][0]["merchant"] == "Amazon"


def test_filter_by_card_keeps_card_list():
    s = summarise_spend(CARDS, card_id="axis-airtel")
    assert s["total_spend"] == 1999.0
    assert [c["card_id"] for c in s["cards"]] == ["hdfc-millennia", "axis-airtel"]


def test_empty_session():
    s = summarise_spend([{"card_id": "x", "card_name": "X", "transactions": []}])
    assert s["months"] == [] and s["total_spend"] == 0 and s["categories"] == []


def test_spend_route_returns_aggregates():
    state = {"session_id": MOCK_SESSION_ID, "cards": CARDS}
    client, patches = _make_client(load_session_return=state)
    try:
        r = client.get(f"/session/{MOCK_SESSION_ID}/spend")
        assert r.status_code == 200
        data = r.json()
        assert data["months"] == ["2024-01", "2024-02", "2024-03"]
        assert data["merchants"][0]["merchant"]

        r = client.get(f"/session/{MOCK_SESSION_ID}/spend", params={"card_id": "axis-airtel"})
        assert r.status_code == 200 and r.json()["total_spend"] == 1999.0

        r = client.get(f"/session/{MOCK_SESSION_ID}/spend", params={"card_id": "nope"})
        assert r.status_code == 404
    finally:
        _stop_patches(patches)


def test_spend_route_unknown_session():
    client, patches = _make_client(load_session_return=None)
    try:
        assert client.get("/session/missing/spend").status_code == 404
    finally:
        _stop_patches(patches)
