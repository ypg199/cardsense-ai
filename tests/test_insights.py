"""agents.insights: rule-based spending notes."""

from __future__ import annotations

from agents.insights import _inr, _streak, spend_insights
from agents.spend_summary import summarise_spend


def _t(date, merchant, amount, category):
    return {
        "date": date,
        "merchant": merchant,
        "amount": amount,
        "transaction_type": "debit",
        "category": category,
        "month": date[:7],
    }


def _insights(txns):
    cards = [{"card_id": "c", "card_name": "C", "transactions": txns}]
    return spend_insights(cards, summarise_spend(cards))


def _by_kind(items):
    return {i["kind"]: i for i in items}


BASE = [
    _t("2024-01-05", "NETFLIX", 649, "entertainment"),
    _t("2024-02-05", "NETFLIX", 649, "entertainment"),
    _t("2024-03-05", "NETFLIX", 649, "entertainment"),
    _t("2024-01-10", "SWIGGY", 2000, "food_delivery"),
    _t("2024-02-10", "SWIGGY", 2200, "food_delivery"),
    _t("2024-03-10", "SWIGGY", 4400, "food_delivery"),
    _t("2024-01-15", "BIGBASKET", 3000, "grocery"),
    _t("2024-02-15", "BIGBASKET", 3100, "grocery"),
    _t("2024-03-15", "BIGBASKET", 2900, "grocery"),
]


def test_month_and_category_changes_lead():
    items = _insights(BASE)
    assert items[0]["kind"] == "month_change"
    assert items[0]["title"] == "Spending up 34% in Mar"
    food = next(i for i in items if i["kind"] == "category_change")
    assert food["title"] == "Food delivery up 100% in Mar" and food["tone"] == "up"
    assert "₹2,200 more" in food["detail"]


def test_recurring_payments_need_every_month_and_steady_amounts():
    rec = _by_kind(_insights(BASE))["recurring"]
    # Swiggy doubled in March, so only Netflix and BigBasket count as regular
    assert rec["title"] == "2 payments repeat every month"
    assert "NETFLIX ₹649" in rec["detail"] and "SWIGGY" not in rec["detail"]


def test_big_one_off_purchase():
    txns = BASE + [_t("2024-03-20", "CROMA", 45000, "shopping_offline")]
    big = _by_kind(_insights(txns))["big_purchase"]
    assert big["title"] == "Biggest purchase: ₹45,000 at CROMA"
    assert "20 Mar" in big["detail"]


def test_streak_and_limits():
    monthly = summarise_spend([{"card_id": "c", "transactions": BASE}])["monthly"]
    assert _streak(monthly)[0]["title"] == "Spending has risen for 3 months in a row"
    items = _insights(BASE)
    assert len(items) <= 5
    assert all(set(i) == {"kind", "tone", "title", "detail"} for i in items)


def test_single_month_has_no_change_insights():
    items = _insights([t for t in BASE if t["month"] == "2024-01"])
    kinds = {i["kind"] for i in items}
    assert not kinds & {"month_change", "category_change", "recurring", "streak"}


def test_empty_session():
    assert _insights([]) == []


def test_indian_grouping():
    assert _inr(173205.06) == "₹1,73,205"
    assert _inr(999) == "₹999"
    assert _inr(12345678) == "₹1,23,45,678"
