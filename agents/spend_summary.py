"""
agents/spend_summary.py
─────────────────────────────────────────────────────────────────────────────
Spend aggregates for the Spend Analyser page.

Turns the parsed transactions of a session into the numbers the charts need:
spend per month, per category per month, top merchants and the largest
purchases. Pure functions, no I/O, so the API route stays thin.

Spend is debits minus refunds. Bill payments and other credits are ignored,
since they are money going into the card, not spending.
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

_MONTH_RE = re.compile(r"^\d{4}-\d{2}")


def _month_of(txn: dict[str, Any]) -> str:
    """Calendar month (YYYY-MM) the purchase happened in, falling back to the statement label."""
    date = str(txn.get("date") or "")
    if _MONTH_RE.match(date):
        return date[:7]
    return str(txn.get("month") or "unknown")


def _signed_amount(txn: dict[str, Any]) -> float:
    """Debits count as spend, refunds reduce it, other credits are skipped (0)."""
    kind = str(txn.get("transaction_type") or "debit").lower()
    try:
        amount = abs(float(txn.get("amount") or 0))
    except (TypeError, ValueError):
        return 0.0
    if kind == "debit":
        return amount
    if kind == "refund":
        return -amount
    return 0.0


def _merchant_key(name: str) -> str:
    return " ".join(name.upper().split())


def summarise_spend(
    cards: list[dict[str, Any]],
    card_id: str | None = None,
    top_merchants: int = 10,
    largest: int = 8,
) -> dict[str, Any]:
    """
    Aggregate spending across cards (or one card when card_id is given).

    Returns a dict with:
      cards          – [{card_id, card_name}] for every card in the session
      months         – sorted YYYY-MM labels that have spending
      total_spend    – net spend over the period
      refunds        – total refunded
      transactions   – number of debit transactions
      monthly        – [{month, total, count, by_category, by_card}]
      categories     – [{category, total, share, count}] largest first
      merchants      – [{merchant, total, count, category}] largest first
      largest        – [{date, merchant, amount, category, card_name}]
    """
    selected = [c for c in cards if card_id is None or c.get("card_id") == card_id]

    month_total: dict[str, float] = defaultdict(float)
    month_count: dict[str, int] = defaultdict(int)
    month_cat: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    month_card: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    cat_total: dict[str, float] = defaultdict(float)
    cat_count: dict[str, int] = defaultdict(int)
    merchants: dict[str, dict[str, Any]] = {}
    debits: list[dict[str, Any]] = []
    refunds = 0.0

    for card in selected:
        for txn in card.get("transactions") or []:
            amount = _signed_amount(txn)
            if amount == 0:
                continue
            month = _month_of(txn)
            category = str(txn.get("category") or "others")
            merchant = str(txn.get("merchant") or "Unknown").strip() or "Unknown"

            month_total[month] += amount
            month_cat[month][category] += amount
            month_card[month][card.get("card_id", "")] += amount
            cat_total[category] += amount

            if amount < 0:
                refunds += -amount
                continue

            month_count[month] += 1
            cat_count[category] += 1
            entry = merchants.setdefault(
                _merchant_key(merchant),
                {"merchant": merchant, "total": 0.0, "count": 0, "category": category},
            )
            entry["total"] += amount
            entry["count"] += 1
            debits.append(
                {
                    "date": txn.get("date") or "",
                    "merchant": merchant,
                    "amount": round(amount, 2),
                    "category": category,
                    "card_name": card.get("card_name", ""),
                }
            )

    months = sorted(m for m in month_total if m != "unknown")
    if "unknown" in month_total:
        months.append("unknown")

    total = sum(month_total.values())
    positive_total = sum(v for v in cat_total.values() if v > 0)

    monthly = [
        {
            "month": m,
            "total": round(max(month_total[m], 0.0), 2),
            "count": month_count[m],
            "by_category": {k: round(v, 2) for k, v in month_cat[m].items() if v > 0},
            "by_card": {k: round(v, 2) for k, v in month_card[m].items() if v > 0},
        }
        for m in months
    ]

    categories = [
        {
            "category": cat,
            "total": round(value, 2),
            "share": round(value / positive_total, 4) if positive_total else 0.0,
            "count": cat_count[cat],
        }
        for cat, value in sorted(cat_total.items(), key=lambda kv: -kv[1])
        if value > 0
    ]

    merchant_rows = sorted(merchants.values(), key=lambda m: -m["total"])[:top_merchants]
    for row in merchant_rows:
        row["total"] = round(row["total"], 2)

    debits.sort(key=lambda d: -d["amount"])

    return {
        "cards": [{"card_id": c.get("card_id", ""), "card_name": c.get("card_name", "")} for c in cards],
        "months": months,
        "total_spend": round(max(total, 0.0), 2),
        "refunds": round(refunds, 2),
        "transactions": sum(month_count.values()),
        "monthly": monthly,
        "categories": categories,
        "merchants": merchant_rows,
        "largest": debits[:largest],
    }
