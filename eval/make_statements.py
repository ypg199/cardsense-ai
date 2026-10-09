"""
eval/make_statements.py
─────────────────────────────────────────────────────────────────────────────
Generate the synthetic credit card statements used by the extraction
benchmark, with a ground-truth JSON file next to each PDF.

All data is fictitious. Each bank uses a different layout, modelled on the
real statement formats (column order, date style, how credits are marked), so
the benchmark checks that parsing isn't tied to one bank's format:

  axis_flipkart     DD/MM/YYYY, separate Dr/Cr column
  axis_airtel_enc   same layout, password-protected, with EMI and a refund
  hdfc_millennia    DD/MM/YYYY HH:MM:SS, reward points column, "Cr" suffix
  hdfc_regalia_2pg  two pages, 60+ rows, page header repeated
  hdfc_infinia_long five pages, 180 rows plus terms and offers text, longer
                    than one Gemini request's text limit
  icici_coral       serial numbers, foreign-currency column, "CR" suffix
  sbi_cashback      "05 Feb 26" dates, "D"/"C" suffix, wrapped descriptions

Run:  python -m eval.make_statements      (rewrites eval/statements/)
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path

import fitz  # PyMuPDF

OUT_DIR = Path(__file__).parent / "statements"
ENCRYPTED_PASSWORD = "SAMP0101"  # documented in eval/README.md

# Statement descriptions per category (the parser's VALID_CATEGORIES). They mix
# clean names with the payment-gateway prefixes and terminal ids real
# statements carry (PYU*, RAZ*, IND*, POS ...).
MERCHANTS: dict[str, list[str]] = {
    "shopping_online": [
        "FLIPKART INTERNET PVT LTD BANGALORE",
        "WWW AMAZON IN BANGALORE IN",
        "IND*FLIPKART PAYMENTS",
        "MYNTRA DESIGNS PVT LTD",
        "PYU*AJIO RELIANCE RETAIL",
        "NYKAA E RETAIL PVT LTD MUMBAI",
    ],
    "shopping_offline": ["SHOPPERS STOP PHOENIX MALL", "RELIANCE TRENDS ANDHERI", "POS 4521 LIFESTYLE INTL"],
    "food_delivery": [
        "PYU*SWIGGY FOOD BANGALORE",
        "ZOMATO LTD GURGAON",
        "RAZ*EATSURE ONLINE",
    ],
    "grocery": [
        "BIGBASKET SUPERMARKET GROCERY",
        "PAYTM*BLINKIT COMMERCE",
        "RAZ*ZEPTO MARKETPLACE",
        "SWIGGY INSTAMART",
        "BBNOW BANGALORE",
    ],
    "travel_flights": [
        "INDIGO 6E 2X4KQ",
        "MMT*MAKEMYTRIP FLIGHTS",
        "IRCTC E-TICKETING NEW DELHI",
        "AIR INDIA WEB",
    ],
    "travel_hotels": ["PAYU*OYO ROOMS GURGAON", "MARRIOTT HOTEL PUNE", "GOIBIBO HOTEL BOOKING"],
    "fuel": ["HPCL-COCO KORAMANGALA", "INDIAN OIL FUEL STATION", "BPCL SERVICE STN 2231"],
    "utility_bills": [
        "BBPS BESCOM BILLPAY",
        "TATA POWER MUMBAI",
        "MAHANAGAR GAS LTD",
        "MSEDCL ONLINE PAYMENT",
    ],
    "airtel_recharge": ["AIRTEL PAYMENTS BANK-RECHARGE", "AIRTEL POSTPAID BILL PAYMENT", "BHARTI AIRTEL LTD"],
    "entertainment": ["BOOKMYSHOW*PVR", "NETFLIX.COM MUMBAI", "PVR INOX CINEMAS", "SPOTIFY INDIA"],
    "healthcare": ["APOLLO PHARMACIES LTD", "PRACTO HEALTH CONSULT", "1MG TECHNOLOGIES"],
    "insurance": ["HDFC LIFE INSURANCE PREMIUM", "ICICI LOMBARD MOTOR INSURANCE", "POLICYBAZAAR INSURANCE"],
    "education": ["COURSERA ONLINE COURSE FEE", "VIT UNIVERSITY FEE PAYMENT", "UDEMY ONLINE COURSES"],
    "rent": ["NOBROKER RENT PAYMENT", "CRED RENTPAY HOUSE RENT"],
}

AMOUNT_RANGE = {
    "travel_flights": (2500, 9000),
    "travel_hotels": (2500, 7000),
    "rent": (15000, 25000),
    "insurance": (3000, 12000),
    "education": (1500, 8000),
    "utility_bills": (600, 3000),
    "fuel": (500, 3000),
}


def _txn(rng: random.Random, day: date, category: str) -> dict:
    lo, hi = AMOUNT_RANGE.get(category, (150, 3500))
    amount = round(rng.uniform(lo, hi), rng.choice([0, 2]))
    return {
        "date": day.isoformat(),
        "description": rng.choice(MERCHANTS[category]),
        "amount": float(amount),
        "transaction_type": "debit",
        "category": category,
    }


def _month_rows(seed: int, year: int, month: int, n_debits: int, categories: list[str]) -> list[dict]:
    """Random debits across the month plus a payment and a cashback credit."""
    rng = random.Random(seed)
    start = date(year, month, 1)
    rows = []
    for _ in range(n_debits):
        day = start + timedelta(days=rng.randint(0, 27))
        rows.append(_txn(rng, day, rng.choice(categories)))
    rows.append(
        {
            "date": (start + timedelta(days=rng.randint(10, 20))).isoformat(),
            "description": "PAYMENT RECEIVED - THANK YOU",
            "amount": float(rng.randint(8, 30) * 1000),
            "transaction_type": "credit",
            "category": "others",
        }
    )
    rows.append(
        {
            "date": (start + timedelta(days=27)).isoformat(),
            "description": "CASHBACK CREDITED",
            "amount": float(rng.randint(80, 600)),
            "transaction_type": "credit",
            "category": "others",
        }
    )
    rows.sort(key=lambda r: r["date"])
    return rows


def _inr(amount: float) -> str:
    """Indian digit grouping: 123456.5 → 1,23,456.50"""
    whole, frac = f"{amount:.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return f"{whole}.{frac}"


TERMS = """IMPORTANT INFORMATION: Please pay at least the Minimum Amount Due by the Payment Due Date to
avoid late payment charges. Finance charges are levied at 3.75% per month on outstanding balances
from the date of transaction if the Total Amount Due is not paid in full. Cash advances attract a
fee of 2.5% subject to a minimum of Rs 500. Reward points are credited within 30 days and expire
after 2 years. GST at 18% applies on all fees, interest and charges. For disputes, contact customer
care within 30 days of the statement date. Never share your OTP, CVV or PIN with anyone. Offers:
get 10% off on dining at partner restaurants, 5X reward points on travel bookings via SmartBuy,
complimentary airport lounge access on spends of Rs 1 lakh per quarter. Terms and conditions apply.""".split(
    "\n"
)


class _Writer:
    """Minimal text-layout helper over PyMuPDF with automatic page breaks."""

    def __init__(self, header_lines: list[tuple[str, int, bool]], column_header: list[tuple[int, str]]):
        self.doc = fitz.open()
        self.header_lines = header_lines
        self.column_header = column_header
        self.page = None
        self.y = 0
        self._new_page()

    def _new_page(self) -> None:
        self.page = self.doc.new_page(width=595, height=842)
        self.y = 50
        for text, size, bold in self.header_lines:
            self.text(40, text, size, bold)
            self.y += size + 8
        self.y += 8
        for x, label in self.column_header:
            self.text(x, label, 8.5, True)
        self.y += 16

    def text(self, x: float, s: str, size: float = 8.5, bold: bool = False) -> None:
        self.page.insert_text((x, self.y), s, fontsize=size, fontname="hebo" if bold else "helv")

    def paragraph(self, lines: list[str]) -> None:
        for line in lines:
            if self.y > 790:
                self._new_page()
            self.text(40, line, 7)
            self.y += 10
        self.y += 8

    def row(self, cells: list[tuple[int, str]], height: int = 14) -> None:
        if self.y > 790:
            self._new_page()
        for x, s in cells:
            self.text(x, s)
        self.y += height

    def save(self, path: Path, password: str | None = None) -> None:
        if password:
            self.doc.save(
                path,
                encryption=fitz.PDF_ENCRYPT_AES_256,
                user_pw=password,
                owner_pw=password + "-owner",
            )
        else:
            self.doc.save(path, garbage=3, deflate=True)


DISCLAIMER = ("SAMPLE STATEMENT - FICTITIOUS DATA FOR TESTING ONLY", 7, False)


def axis(name: str, rows: list[dict], period: str, password: str | None = None) -> _Writer:
    w = _Writer(
        [
            (f"Axis Bank {name} Credit Card Statement", 14, True),
            DISCLAIMER,
            (f"Card No: 5334 XXXX XXXX 0000    Statement Period: {period}", 8.5, False),
        ],
        [(40, "Date"), (110, "Transaction Details"), (420, "Amount (Rs.)"), (510, "Dr/Cr")],
    )
    for r in rows:
        d = date.fromisoformat(r["date"]).strftime("%d/%m/%Y")
        dc = "Dr" if r["transaction_type"] == "debit" else "Cr"
        w.row([(40, d), (110, r["description"]), (420, _inr(r["amount"])), (515, dc)])
    return w


def hdfc(name: str, rows: list[dict], period: str, seed: int) -> _Writer:
    rng = random.Random(seed)
    w = _Writer(
        [
            (f"HDFC Bank {name} Credit Card", 14, True),
            DISCLAIMER,
            (f"Statement for card ending 0000    Billing Period {period}", 8.5, False),
            ("Domestic Transactions", 10, True),
        ],
        [(40, "Date"), (150, "Transaction Description"), (420, "Reward Points"), (490, "Amount (in Rs.)")],
    )
    for r in rows:
        d = date.fromisoformat(r["date"]).strftime("%d/%m/%Y")
        stamp = f"{d} {rng.randint(8, 22):02d}:{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d}"
        pts = "" if r["transaction_type"] != "debit" else str(int(r["amount"] // 150))
        amt = _inr(r["amount"]) + (" Cr" if r["transaction_type"] != "debit" else "")
        w.row([(40, stamp), (150, r["description"][:42]), (440, pts), (490, amt)])
    return w


def icici(name: str, rows: list[dict], period: str) -> _Writer:
    w = _Writer(
        [
            (f"ICICI Bank {name} Credit Card Statement", 14, True),
            DISCLAIMER,
            (f"Statement period : {period}", 8.5, False),
        ],
        [
            (40, "Date"),
            (100, "SerNo."),
            (160, "Transaction Details"),
            (390, "Intl.# amount"),
            (490, "Amount (in`)"),
        ],
    )
    for i, r in enumerate(rows):
        d = date.fromisoformat(r["date"]).strftime("%d/%m/%Y")
        intl = r.get("intl", "")
        amt = _inr(r["amount"]) + (" CR" if r["transaction_type"] != "debit" else "")
        w.row([(40, d), (100, str(10293840 + i * 7)), (160, r["description"][:38]), (390, intl), (490, amt)])
    return w


def sbi(name: str, rows: list[dict], period: str) -> _Writer:
    w = _Writer(
        [
            (f"{name} SBI Card - Monthly Statement", 14, True),
            DISCLAIMER,
            (f"Statement Period: {period}", 8.5, False),
            ("TRANSACTIONS FOR CARD XXXX XXXX XXXX 0000", 9, True),
        ],
        [(40, "Date"), (110, "Transaction Details"), (480, "Amount ( `)")],
    )
    for r in rows:
        d = date.fromisoformat(r["date"]).strftime("%d %b %y")
        suffix = " D" if r["transaction_type"] == "debit" else " C"
        desc = r["description"]
        # Long descriptions wrap onto a second line, as on real SBI statements
        if len(desc) > 26:
            cut = desc.rfind(" ", 0, 26)
            w.row([(40, d), (110, desc[:cut]), (480, _inr(r["amount"]) + suffix)], height=11)
            w.row([(110, desc[cut + 1 :])])
        else:
            w.row([(40, d), (110, desc), (480, _inr(r["amount"]) + suffix)])
    return w


ALL = list(MERCHANTS)


def build() -> list[str]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    made: list[str] = []

    def emit(key: str, writer: _Writer, rows: list[dict], bank: str, password: str | None = None):
        writer.save(OUT_DIR / f"{key}.pdf", password)
        truth = {"bank": bank, "password": password, "transactions": rows}
        (OUT_DIR / f"{key}.json").write_text(json.dumps(truth, indent=2) + "\n")
        made.append(key)

    rows = _month_rows(1, 2026, 2, 16, ["shopping_online"] * 3 + ALL)
    emit("axis_flipkart", axis("Flipkart", rows, "01/02/2026 - 28/02/2026"), rows, "Axis Bank")

    rows = _month_rows(2, 2026, 3, 14, ["airtel_recharge", "utility_bills", "food_delivery", "grocery"] + ALL)
    rows += [
        {
            "date": "2026-03-05",
            "description": "EMI 3/12 SMARTPHONE PRINCIPAL+INTEREST",
            "amount": 2416.67,
            "transaction_type": "debit",
            "category": "emi",
        },
        {
            "date": "2026-03-19",
            "description": "REFUND AMAZON PAY INDIA ORDER 402-11",
            "amount": 899.0,
            "transaction_type": "refund",
            "category": "shopping_online",
        },
    ]
    rows.sort(key=lambda r: r["date"])
    emit(
        "axis_airtel_enc",
        axis("Airtel", rows, "01/03/2026 - 31/03/2026"),
        rows,
        "Axis Bank",
        ENCRYPTED_PASSWORD,
    )

    rows = _month_rows(3, 2026, 1, 18, ["shopping_online", "food_delivery", "grocery"] + ALL)
    emit("hdfc_millennia", hdfc("Millennia", rows, "01 Jan 2026 - 31 Jan 2026", 3), rows, "HDFC Bank")

    rows = _month_rows(4, 2026, 4, 60, ALL)
    emit("hdfc_regalia_2pg", hdfc("Regalia Gold", rows, "01 Apr 2026 - 30 Apr 2026", 4), rows, "HDFC Bank")

    rows = _month_rows(5, 2026, 5, 17, ALL)
    rows.append(
        {
            "date": "2026-05-14",
            "description": "SPOTIFY AB STOCKHOLM",
            "amount": 1089.36,
            "transaction_type": "debit",
            "category": "entertainment",
            "intl": "USD 12.99",
        }
    )
    rows.sort(key=lambda r: r["date"])
    emit("icici_coral", icici("Coral", rows, "May 1, 2026 to May 31, 2026"), rows, "ICICI Bank")

    rows = _month_rows(6, 2026, 6, 18, ["shopping_online"] * 2 + ALL)
    emit("sbi_cashback", sbi("CASHBACK", rows, "01 Jun 26 to 30 Jun 26"), rows, "SBI Card")

    rows = _month_rows(7, 2026, 7, 180, ALL)
    w = _Writer(
        [
            ("HDFC Bank Infinia Credit Card", 14, True),
            DISCLAIMER,
            ("Billing Period 01 Jul 2026 - 31 Jul 2026", 8.5, False),
        ],
        [(40, "Date"), (150, "Transaction Description"), (420, "Reward Points"), (490, "Amount (in Rs.)")],
    )
    w.paragraph(TERMS * 2)  # long front matter, as on real premium-card statements
    for r in rows:
        d = date.fromisoformat(r["date"]).strftime("%d/%m/%Y")
        amt = _inr(r["amount"]) + (" Cr" if r["transaction_type"] != "debit" else "")
        pts = str(int(r["amount"] // 150)) if r["transaction_type"] == "debit" else ""
        w.row([(40, d), (150, r["description"][:42]), (440, pts), (490, amt)])
    emit("hdfc_infinia_long", w, rows, "HDFC Bank")

    return made


if __name__ == "__main__":
    for key in build():
        print("wrote", OUT_DIR / f"{key}.pdf")
