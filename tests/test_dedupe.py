"""
tests/test_dedupe.py
─────────────────────────────────────────────────────────────────────────────
Duplicate cards: the shared card key, the duplicate report, and the crawler
and seed paths that used to store the same card twice.
Everything is mocked — no network, Gemini or MongoDB.
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest.mock as mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crawler import card_crawler as cc
from db.card_keys import bank_key, card_key
from db.dedupe_cards import find_duplicates, find_lookalikes, report
from tests.test_crawler_quality import GOOD_CARD, PAGE_HTML, _browser_returning


def card(_id, name, bank, **extra):
    return {"_id": _id, "name": name, "bank": bank, **extra}


# ── Card key ────────────────────────────────────────────────────────────────


def test_card_key_ignores_bank_words_and_aliases():
    assert card_key("Axis Bank", "Flipkart Axis Bank Credit Card") == card_key("Axis", "Flipkart")
    assert card_key("State Bank of India", "SBI Card ELITE") == "sbi-elite"
    assert card_key("SBI Card", "SBI Card ELITE") == "sbi-elite"
    assert bank_key("HDFC Bank Ltd") == "hdfc"


# ── Duplicate report ────────────────────────────────────────────────────────


def test_same_card_under_two_ids_is_grouped_and_best_record_kept():
    old = card("axis-bank-airtel-credit-card", "Axis Bank Airtel Credit Card", "Axis Bank", benefits=[{}])
    new = card(
        "axis-airtel",
        "Airtel Axis Bank Credit Card",
        "Axis Bank",
        content_hash="h",
        embedding=[0.1],
        benefits=[{}, {}],
        last_crawled="2026-10-09",
    )
    other = card("axis-magnus", "Magnus", "Axis Bank")
    groups = find_duplicates([old, new, other])
    assert len(groups) == 1
    assert groups[0]["keep"]["_id"] == "axis-airtel"
    assert [d["_id"] for d in groups[0]["remove"]] == ["axis-bank-airtel-credit-card"]


def test_same_page_with_different_names_is_grouped():
    url = "https://www.hdfc.bank.in/credit-cards/millennia-credit-card"
    a = card("hdfc-millennia", "Millennia", "HDFC Bank", source_url=url, content_hash="x")
    b = card("hdfc-millenia-cc", "Millenia CC", "HDFC Bank", source_url=url + "/?utm=1")
    groups = find_duplicates([a, b])
    assert len(groups) == 1 and groups[0]["keep"]["_id"] == "hdfc-millennia"


def test_seed_amazon_card_matches_crawled_amazon_pay_card():
    seed = card("icici-amazon", "Amazon Pay ICICI Card", "ICICI Bank")
    crawled = card("icici-amazon-pay", "Amazon Pay ICICI Bank Credit Card", "ICICI Bank", content_hash="h")
    groups = find_duplicates([seed, crawled])
    assert groups[0]["keep"]["_id"] == "icici-amazon-pay"


def test_different_cards_are_not_grouped_but_lookalikes_are_listed():
    docs = [
        card("hdfc-regalia", "Regalia", "HDFC Bank"),
        card("hdfc-regalia-gold", "Regalia Gold", "HDFC Bank"),
        card("axis-regalia", "Regalia", "Axis Bank"),  # another bank: not a lookalike
    ]
    assert find_duplicates(docs) == []
    pairs = find_lookalikes(docs)
    assert [(a["_id"], b["_id"]) for a, b in pairs] == [("hdfc-regalia", "hdfc-regalia-gold")]
    text = report(docs, [], pairs)
    assert "3 cards stored, 3 unique, 0 duplicate records" in text and "Regalia Gold" in text


# ── Crawler reuses the stored id for a page it crawled before ──────────────


def test_recrawl_with_new_name_updates_the_stored_card():
    browser, _ = _browser_returning(PAGE_HTML)
    upsert = mock.AsyncMock(return_value=True)
    stored = {"_id": "axis-flipkart-old", "name": "Flipkart", "content_hash": "stale"}
    with (
        mock.patch.object(cc, "_find_stored_card", mock.AsyncMock(return_value=stored)),
        mock.patch.object(cc, "_call_gemini_flash", return_value=GOOD_CARD),
        mock.patch.object(cc, "_generate_embedding", return_value=([0.1], "text")),
        mock.patch.object(cc, "_upsert_card", upsert),
        mock.patch("asyncio.sleep", mock.AsyncMock()),
    ):
        result = asyncio.run(cc.crawl_url("https://www.axis.bank.in/cards/credit-card/x", browser=browser))
    assert result["success"] and not result["unchanged"]
    assert upsert.await_args.args[0]["_id"] == "axis-flipkart-old"


def test_stored_card_lookup_matches_url_variants():
    variants = cc._url_variants("https://www.axis.bank.in/cards/x/")
    assert "https://www.axis.bank.in/cards/x" in variants
    assert "https://www.axis.bank.in/cards/x/" in variants


# ── Seeding skips a card the crawler stored under another id ───────────────


def test_seed_skips_card_crawled_under_another_id():
    from db import seed

    class Cursor:
        def __init__(self, docs):
            self._it = iter(docs)

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self._it)
            except StopIteration:
                raise StopAsyncIteration from None

    crawled = [{"_id": "icici-amazon-pay", "bank": "ICICI Bank", "name": "Amazon Pay ICICI Credit Card"}]
    col = mock.MagicMock()
    col.find = mock.MagicMock(return_value=Cursor(crawled))
    col.update_one = mock.AsyncMock(return_value=mock.MagicMock(upserted_id=None, modified_count=1))
    db = mock.MagicMock()
    db.__getitem__ = mock.MagicMock(return_value=col)

    with (
        mock.patch("db.connection.ping_db", mock.AsyncMock(return_value=True)),
        mock.patch("db.connection.get_db", return_value=db),
        mock.patch("db.connection.close_db", mock.AsyncMock()),
    ):
        asyncio.run(seed.seed_cards())

    written = {c.args[0]["_id"] for c in col.update_one.await_args_list}
    assert "icici-amazon" not in written
    assert "axis-flipkart" in written
