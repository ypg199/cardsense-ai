"""
crawler/sources.py
─────────────────────────────────────────────────────────────────────────────
Sources to crawl for Indian credit card data.
Section 8 of the spec defines these exact sources.

Each entry in SOURCES is a dict:
  key      — short identifier used in API / the crawl task
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

# ── Bank sources ─────────────────────────────────────────────────────────────
# Indian banks moved their sites to *.bank.in in 2025; the old domains redirect.
# Each bank has a listing page we scan for product links (link_pattern), plus
# known product pages so a crawl still has work if link discovery finds nothing
# (for example when the listing renders its cards with JavaScript).
BANK_SOURCES = {
    "axis": {
        "bank": "Axis Bank",
        "listing_url": "https://www.axis.bank.in/cards/credit-card",
        "link_pattern": r"^https://www\.axis\.bank\.in/cards/credit-card/[a-z0-9-]+$",
        "card_urls": [
            "https://www.axis.bank.in/cards/credit-card/flipkart-axisbank-credit-card",
            "https://www.axis.bank.in/cards/credit-card/airtel-axis-bank-credit-card",
            "https://www.axis.bank.in/cards/credit-card/axis-bank-my-zone-credit-card",
            "https://www.axis.bank.in/cards/credit-card/axis-bank-neo-credit-card",
            "https://www.axis.bank.in/cards/credit-card/rewards-credit-card",
            "https://www.axis.bank.in/cards/credit-card/indianoil-axis-bank-credit-card",
            "https://www.axis.bank.in/cards/credit-card/axis-bank-select-credit-card",
            "https://www.axis.bank.in/cards/credit-card/axis-bank-magnus-credit-card",
            "https://www.axis.bank.in/cards/credit-card/axis-horizon-credit-card",
            "https://www.axis.bank.in/cards/credit-card/indigo-axis-bank-credit-card",
        ],
    },
    "hdfc": {
        "bank": "HDFC Bank",
        "listing_url": "https://www.hdfc.bank.in/credit-cards",
        "link_pattern": r"^https://(www\.)?hdfc\.bank\.in/credit-cards/[a-z0-9-]+-credit-card$",
        "card_urls": [
            "https://www.hdfc.bank.in/credit-cards/millennia-credit-card",
        ],
    },
    "icici": {
        "bank": "ICICI Bank",
        "listing_url": "https://www.icici.bank.in/personal-banking/cards/credit-card",
        "link_pattern": r"^https://www\.icici\.bank\.in/personal-banking/cards/credit-card/[a-z0-9-]+$",
        "card_urls": [
            "https://www.icici.bank.in/personal-banking/cards/credit-card/coral-credit-card",
            "https://www.icici.bank.in/personal-banking/cards/credit-card/rubyx-credit-card",
            "https://www.icici.bank.in/personal-banking/cards/credit-card/sapphiro-card",
            "https://www.icici.bank.in/personal-banking/cards/credit-card/coral-rupay-card",
        ],
    },
    "sbi": {
        "bank": "SBI Card",
        "listing_url": "https://www.sbicard.com/en/personal/credit-cards.html",
        # Cards sit one or two folders deep: /credit-cards/rewards/x.page or /credit-cards/x.page
        "link_pattern": r"^https://www\.sbicard\.com/en/personal/credit-cards/([a-z0-9-]+/)?[a-z0-9-]+\.page$",
        "card_urls": [
            "https://www.sbicard.com/en/personal/credit-cards/rewards/cashback-sbi-card.page",
        ],
    },
}

# Links under a bank's card section that are not individual card products
NON_PRODUCT_LINK_WORDS = (
    "apply",
    "compare",
    "fixed-deposit",
    "loan",
    "emi",
    "offer",
    "faq",
    "eligibility",
    "fees",
    "charges",
    "pre-approved",
    "simplyfier",
    "business",
    "corporate",
    "nri",
    "faqs",
    "help",
    "block",
    "pin",
    "lost",
    "stolen",
    "statement",
    "how",
    "track",
    "status",
    "upgrade",
    "tnc",
    "terms",
)

# ── Direct bank URLs (known product pages across all banks) ──────────────────
DIRECT_BANK_URLS = [url for src in BANK_SOURCES.values() for url in src["card_urls"]]

# ── Default crawl: every bank source; aggregators stay opt-in ────────────────
BANK_SOURCE_KEYS = list(BANK_SOURCES.keys())

# Aggregator sites block headless browsers, so they only run when asked for
ALL_SOURCE_KEYS: list[str] = []

# ── Frequent crawl — direct bank URLs only (catches rate changes) ─────────────
FREQUENT_CRAWL_URLS = DIRECT_BANK_URLS[:]
