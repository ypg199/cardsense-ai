"""
crawler/sources.py
─────────────────────────────────────────────────────────────────────────────
Sources to crawl for Indian credit card data.
Section 8 of the spec defines these exact sources.

Each entry in SOURCES is a dict:
  key      — short identifier used in API / Celery tasks
  url      — base URL to start crawl from
  selector — CSS selector for card link elements
  paginated — whether the source has multiple pages
─────────────────────────────────────────────────────────────────────────────
"""

# ── Aggregator sources ───────────────────────────────────────────────────────
SOURCES = {
    "cardinsider": {
        "url": "https://www.cardinsider.com/credit-cards/",
        "selector": "a.card-name-link",
        "paginated": True,
        "description": "CardInsider — largest Indian card comparison portal",
    },
    "bankbazaar": {
        "url": "https://www.bankbazaar.com/credit-card.html",
        "selector": "a.card-title",
        "paginated": True,
        "description": "BankBazaar — major financial marketplace",
    },
    "paisabazaar": {
        "url": "https://www.paisabazaar.com/credit-card/",
        "selector": "a.cardTitle",
        "paginated": False,
        "description": "PaisaBazaar — financial products comparison",
    },
}

# ── Direct bank URLs ──────────────────────────────────────────────────────────
DIRECT_BANK_URLS = [
    # Axis Bank
    # "https://www.axisbank.com/retail/cards/credit-card",
    # HDFC Bank
    # "https://www.hdfcbank.com/personal/pay/cards/credit-cards",
    # SBI Card
    "https://www.sbicard.com/en/personal/credit-cards.html#premium",
    # ICICI Bank
    # "https://www.icicibank.com/personal-banking/cards",
]

# ── All source keys for the daily full crawl ─────────────────────────────────
ALL_SOURCE_KEYS = []
# list(SOURCES.keys())

# ── Frequent crawl — direct bank URLs only (catches rate changes) ─────────────
FREQUENT_CRAWL_URLS = DIRECT_BANK_URLS[:]
