"""
agents/insights.py
─────────────────────────────────────────────────────────────────────────────
Short, plain-language notes about a user's spending ("Food delivery up 40%
in April", "3 payments repeat every month").

Rule-based on purpose: every sentence is backed by numbers computed here, so
an insight can never contradict the charts next to it. Pure functions, no I/O.
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from collections import defaultdict
from statistics import median
from typing import Any

from agents.spend_summary import _merchant_key, _month_of, _signed_amount

MAX_INSIGHTS = 5

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _month_name(m: str) -> str:
    try:
        return _MONTHS[int(m[5:7]) - 1]
    except (ValueError, IndexError):
        return m


def _inr(v: float) -> str:
    """₹ with Indian digit grouping: 1,73,205."""
    n = round(abs(v))
    s = str(n)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups) + "," + tail
    return f"₹{s}"


def _cat(c: str) -> str:
    return c.replace("_", " ").capitalize()


def _insight(kind: str, tone: str, title: str, detail: str, score: float) -> dict[str, Any]:
    return {"kind": kind, "tone": tone, "title": title, "detail": detail, "_score": score}


def _month_change(monthly: list[dict]) -> list[dict]:
    if len(monthly) < 2:
        return []
    prev, last = monthly[-2], monthly[-1]
    if prev["total"] <= 0:
        return []
    pct = (last["total"] - prev["total"]) / prev["total"] * 100
    if abs(pct) < 10:
        return []
    up = pct > 0
    return [
        _insight(
            "month_change",
            "up" if up else "down",
            f"Spending {'up' if up else 'down'} {abs(pct):.0f}% in {_month_name(last['month'])}",
            f"{_inr(last['total'])} against {_inr(prev['total'])} in {_month_name(prev['month'])}.",
            abs(pct) + 1000,  # the headline change always leads
        )
    ]


def _category_movers(monthly: list[dict]) -> list[dict]:
    if len(monthly) < 2:
        return []
    prev, last = monthly[-2]["by_category"], monthly[-1]["by_category"]
    movers = []
    for cat in set(prev) | set(last):
        a, b = prev.get(cat, 0.0), last.get(cat, 0.0)
        diff = b - a
        if abs(diff) < 1000 or a <= 0:
            continue
        pct = diff / a * 100
        if abs(pct) < 25:
            continue
        movers.append((abs(diff), cat, a, b, pct))
    movers.sort(reverse=True)
    out = []
    month = _month_name(monthly[-1]["month"])
    for size, cat, a, b, pct in movers[:2]:
        up = pct > 0
        out.append(
            _insight(
                "category_change",
                "up" if up else "down",
                f"{_cat(cat)} {'up' if up else 'down'} {abs(pct):.0f}% in {month}",
                f"{_inr(abs(b - a))} {'more' if up else 'less'} than the month before ({_inr(b)} vs {_inr(a)}).",
                abs(pct) * 0.8 + size / 1000,
            )
        )
    return out


def _recurring(selected: list[dict], months: list[str]) -> list[dict]:
    """Merchants charged in every month (at least 3), with steady amounts."""
    if len(months) < 3:
        return []
    by_merchant: dict[str, dict[str, Any]] = {}
    for card in selected:
        for t in card.get("transactions") or []:
            amount = _signed_amount(t)
            if amount <= 0:
                continue
            key = _merchant_key(str(t.get("merchant") or ""))
            row = by_merchant.setdefault(key, {"name": t.get("merchant"), "months": defaultdict(float)})
            row["months"][_month_of(t)] += amount
    repeat = []
    for row in by_merchant.values():
        amounts = [row["months"].get(m, 0.0) for m in months]
        if min(amounts) <= 0 or max(amounts) > 1.6 * min(amounts):
            continue
        repeat.append((sum(amounts) / len(amounts), row["name"]))
    if not repeat:
        return []
    repeat.sort(reverse=True)
    total = sum(a for a, _ in repeat)
    names = ", ".join(f"{name} {_inr(a)}" for a, name in repeat[:3])
    more = f" and {len(repeat) - 3} more" if len(repeat) > 3 else ""
    n = len(repeat)
    return [
        _insight(
            "recurring",
            "info",
            f"{n} payment{'s' if n > 1 else ''} repeat every month",
            f"About {_inr(total)} a month: {names}{more}.",
            30 + n,
        )
    ]


def _concentration(summary: dict) -> list[dict]:
    total = summary["total_spend"]
    out = []
    if total > 0 and summary["merchants"]:
        top = summary["merchants"][0]
        share = top["total"] / total * 100
        if share >= 12:
            out.append(
                _insight(
                    "top_merchant",
                    "info",
                    f"{share:.0f}% of your spend went to {top['merchant']}",
                    f"{_inr(top['total'])} over {top['count']} purchase{'s' if top['count'] != 1 else ''}.",
                    share,
                )
            )
    if summary["categories"]:
        cat = summary["categories"][0]
        if cat["share"] >= 0.3:
            out.append(
                _insight(
                    "top_category",
                    "info",
                    f"{_cat(cat['category'])} is {cat['share'] * 100:.0f}% of your spending",
                    f"{_inr(cat['total'])} in total. A card that rewards it well pays off most.",
                    cat["share"] * 100,
                )
            )
    return out


def _big_purchase(selected: list[dict], summary: dict) -> list[dict]:
    amounts = [_signed_amount(t) for c in selected for t in c.get("transactions") or []]
    amounts = [a for a in amounts if a > 0]
    if len(amounts) < 8 or not summary["largest"]:
        return []
    big = summary["largest"][0]
    typical = median(amounts)
    if big["amount"] < 5000 or big["amount"] < 4 * typical:
        return []
    date = str(big.get("date") or "")
    when = f" on {int(date[8:10])} {_month_name(date)}" if len(date) >= 10 else ""
    return [
        _insight(
            "big_purchase",
            "info",
            f"Biggest purchase: {_inr(big['amount'])} at {big['merchant']}",
            f"{big['amount'] / typical:.0f}x your typical purchase of {_inr(typical)}{when}.",
            45,
        )
    ]


def _streak(monthly: list[dict]) -> list[dict]:
    totals = [m["total"] for m in monthly]
    if len(totals) < 3:
        return []
    up = all(b > a for a, b in zip(totals[-3:], totals[-2:], strict=False))
    down = all(b < a for a, b in zip(totals[-3:], totals[-2:], strict=False))
    if not (up or down):
        return []
    word = "risen" if up else "fallen"
    return [
        _insight(
            "streak",
            "up" if up else "down",
            f"Spending has {word} for 3 months in a row",
            f"From {_inr(totals[-3])} in {_month_name(monthly[-3]['month'])} to {_inr(totals[-1])} "
            f"in {_month_name(monthly[-1]['month'])}.",
            25,
        )
    ]


def spend_insights(
    cards: list[dict[str, Any]], summary: dict[str, Any], card_id: str | None = None
) -> list[dict]:
    """
    Up to MAX_INSIGHTS notes for a spend summary (from summarise_spend),
    strongest first. Each is {kind, tone, title, detail}; tone is "up",
    "down" or "info" so the UI can pick an icon without parsing text.
    """
    selected = [c for c in cards if card_id is None or c.get("card_id") == card_id]
    monthly = [m for m in summary["monthly"] if m["month"] != "unknown"]
    found = (
        _month_change(monthly)
        + _category_movers(monthly)
        + _recurring(selected, [m["month"] for m in monthly])
        + _streak(monthly)
        + _concentration(summary)
        + _big_purchase(selected, summary)
    )
    found.sort(key=lambda i: i["_score"], reverse=True)
    for i in found:
        i.pop("_score")
    return found[:MAX_INSIGHTS]
