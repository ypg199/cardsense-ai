"""
eval/make_sample.py
─────────────────────────────────────────────────────────────────────────────
Build the sample statements behind the "Try it with sample data" button.

Writes four months of a fictitious HDFC Millennia statement:

  frontend/public/samples/hdfc_millennia_2026-0N.pdf   downloadable PDFs
  api/sample/hdfc_millennia.json                       the same transactions,
                                                       already parsed, so the
                                                       demo skips the AI parse

All data is made up. Run:  python -m eval.make_sample
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import calendar
import json
from pathlib import Path

from eval.make_statements import _month_rows, hdfc

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "frontend" / "public" / "samples"
JSON_PATH = ROOT / "api" / "sample" / "hdfc_millennia.json"

CARD_ID = "hdfc-millennia"
MONTHS = [(2026, 1), (2026, 2), (2026, 3), (2026, 4)]
# Weighted towards Millennia's 5% partners, with some spend it doesn't reward
CATEGORIES = (
    ["shopping_online"] * 3
    + ["food_delivery"] * 3
    + ["entertainment", "grocery", "grocery", "fuel", "utility_bills", "travel_flights", "healthcare"]
)


def build() -> dict:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    months = []
    for i, (year, month) in enumerate(MONTHS):
        label = f"{year}-{month:02d}"
        rows = _month_rows(100 + i, year, month, 16 + (i * 3) % 5, CATEGORIES)
        last = calendar.monthrange(year, month)[1]
        period = f"01 {calendar.month_abbr[month]} {year} - {last} {calendar.month_abbr[month]} {year}"
        hdfc("Millennia", rows, period, 100 + i).save(PDF_DIR / f"hdfc_millennia_{label}.pdf", None)
        months.append(
            {
                "month": label,
                "transactions": [
                    {
                        "date": r["date"],
                        "merchant": r["description"],
                        "amount": r["amount"],
                        "transaction_type": r["transaction_type"],
                        "category": r["category"],
                        "month": label,
                    }
                    for r in rows
                ],
            }
        )
    data = {"card_id": CARD_ID, "note": "Fictitious sample data", "months": months}
    JSON_PATH.write_text(json.dumps(data, indent=1) + "\n")
    return data


if __name__ == "__main__":
    out = build()
    print(
        f"Wrote {len(out['months'])} months to {JSON_PATH.relative_to(ROOT)} and {PDF_DIR.relative_to(ROOT)}/"
    )
