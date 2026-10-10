"""
db/card_keys.py
─────────────────────────────────────────────────────────────────────────────
How a card is identified. The crawler uses card_key() as the _id of a newly
found card, and the seed and duplicate checks use the same key to tell
whether two records describe the same card.
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit, urlunsplit

_FILLER_WORDS = {"bank", "card", "credit", "the", "of"}
# Banks that go by more than one name, keyed by the first word of the long form
_BANK_ALIASES = {"state": "sbi"}


def _words(text: str) -> list[str]:
    return [w for w in re.split(r"[^a-z0-9]+", (text or "").lower()) if w]


def card_key(bank: str, name: str) -> str:
    """
    A short, stable id: "<bank>-<card words>", truncated to 80 chars.

    The bank's own words and filler like "Credit Card" are dropped from the
    card name, so "Flipkart Axis Bank Credit Card" by "Axis Bank" becomes
    "axis-flipkart" (the same id as the seed card, which it then replaces).
    "State Bank of India" and "SBI Card" both give the "sbi" prefix.
    """
    bank_words = [w for w in _words(bank) if w not in _FILLER_WORDS]
    prefix = [_BANK_ALIASES.get(w, w) for w in (bank_words[:1] or _words(bank)[:1])]
    dropped = set(bank_words) | set(prefix)
    name_words = [w for w in _words(name) if w not in _FILLER_WORDS and w not in dropped]
    return "-".join(prefix + (name_words or _words(name)))[:80].strip("-")


def bank_key(bank: str) -> str:
    """The bank part of card_key(), e.g. "axis" for "Axis Bank Ltd"."""
    return card_key(bank, "").split("-")[0]


def normalize_url(href: str, base_url: str = "") -> str:
    """Absolute URL without query string, fragment or trailing slash."""
    parts = urlsplit(urljoin(base_url, href or ""))
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path.rstrip("/"), "", ""))
