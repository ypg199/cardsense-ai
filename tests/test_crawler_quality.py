"""
tests/test_crawler_quality.py
─────────────────────────────────────────────────────────────────────────────
Crawler data quality and reliability: link discovery, validation of Gemini
output, unchanged-page skipping, and protection of crawled data from reseeding.
Everything is mocked — no network, Gemini or MongoDB.
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest.mock as mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.parse_node import VALID_CATEGORIES
from crawler import card_crawler as cc
from crawler.sources import BANK_SOURCES

GOOD_CARD = {
    "name": "Flipkart Axis Bank Credit Card",
    "bank": "Axis Bank",
    "network": "visa",
    "card_type": "Co-Branded",
    "annual_fee": "₹500 + GST",
    "fee_waiver_spend": "Rs. 3,50,000",
    "joining_fee": "Nil",
    "benefits": [
        {"category": "shopping_online", "label": "Flipkart", "rate": 5, "merchant_keywords": ["FLIPKART"]},
        {"category": "online_shopping", "label": "Partners", "rate": "4%"},
        {"category": "lounge_access", "label": "Lounge", "rate": 0.1},
        {"category": "others", "label": "Everything else", "rate": 0.01},
        {"category": "fuel", "label": "Typo", "rate": 75},
    ],
    "utilization_questions": [
        {"id": "q_fk", "text": "Do you shop on Flipkart?", "maps_to_category": "shopping_online"},
        {"id": "q_fk", "text": "Do you buy groceries?", "maps_to_category": "grocery"},
        {"id": "q_base", "text": "Do you use it for everyday spends?", "maps_to_category": "others"},
    ],
    "best_for_tags": ["flipkart shoppers"],
}


# ── Link discovery ──────────────────────────────────────────────────────────


def test_discover_card_links_filters_and_dedupes():
    axis = BANK_SOURCES["axis"]
    hrefs = [
        "/cards/credit-card/flipkart-axisbank-credit-card",
        "https://www.axis.bank.in/cards/credit-card/flipkart-axisbank-credit-card?cta=hero#top",
        "/cards/credit-card/axis-bank-magnus-credit-card/",
        "/cards/credit-card/indigo-axis-bank-premium-credit-card",
        "/cards/credit-card/credit-card-emi",
        "/cards/credit-card/credit-card-against-fixed-deposit",
        "/cards/credit-card/instant-loan-on-credit-card",
        "/cards/credit-card/flipkart-axisbank-credit-card/apply",
        "https://www.example.com/cards/credit-card/some-card",
        "javascript:void(0)",
        "",
    ]
    links = cc.discover_card_links(hrefs, axis["listing_url"], axis["link_pattern"])
    assert links == [
        "https://www.axis.bank.in/cards/credit-card/flipkart-axisbank-credit-card",
        "https://www.axis.bank.in/cards/credit-card/axis-bank-magnus-credit-card",
        "https://www.axis.bank.in/cards/credit-card/indigo-axis-bank-premium-credit-card",
    ]


def test_discover_bank_cards_falls_back_to_known_pages():
    async def boom(*_args, **_kwargs):
        raise TimeoutError("listing blocked")

    with mock.patch.object(cc, "_listing_hrefs", side_effect=boom):
        urls = asyncio.run(cc.discover_bank_cards(browser=None, source_key="hdfc"))
    assert urls == BANK_SOURCES["hdfc"]["card_urls"]


def test_discover_bank_cards_merges_discovered_first():
    hdfc = BANK_SOURCES["hdfc"]
    discovered = ["/credit-cards/regalia-gold-credit-card", "/credit-cards/millennia-credit-card"]

    async def hrefs(*_args, **_kwargs):
        return discovered

    with mock.patch.object(cc, "_listing_hrefs", side_effect=hrefs):
        urls = asyncio.run(cc.discover_bank_cards(browser=None, source_key="hdfc"))
    assert urls[0] == "https://www.hdfc.bank.in/credit-cards/regalia-gold-credit-card"
    assert urls.count(hdfc["card_urls"][0]) == 1


# ── HTML cleaning ───────────────────────────────────────────────────────────


def test_clean_html_prefers_main_and_drops_repeated_lines():
    menu = "<div>Personal Loans</div><div>Home Loans</div>" * 3
    body = "<p>Earn 5% cashback on Flipkart.</p>" * 2 + "<p>" + "Annual fee Rs 500. " * 20 + "</p>"
    html = f"<html><body>{menu}<main>{body}</main></body></html>"
    text = cc._clean_html(html)
    assert "Personal Loans" not in text
    assert text.count("Earn 5% cashback on Flipkart.") == 1


# ── Validation of Gemini output ─────────────────────────────────────────────


def test_normalize_card_coerces_fields():
    card = cc.normalize_card(GOOD_CARD)
    assert card["network"] == "Visa"
    assert card["card_type"] == "co-branded"
    assert card["annual_fee"] == 500
    assert card["fee_waiver_spend"] == 350000
    assert card["joining_fee"] == 0


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("₹500 + GST", 500),
        ("Rs. 2,00,000", 200000),
        ("₹499, waived on spends of ₹1 lakh", 499),
        ("Lifetime free", 0),
        ("Nil", 0),
        (750.0, 750),
        ("not mentioned", None),
        (None, None),
    ],
)
def test_amount_parsing(value, expected):
    assert cc._to_amount(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0.05, 0.05), (5, 0.05), ("1.5%", 0.015), (1, 0.01), (75, None), (0, None), ("abc", None)],
)
def test_rate_parsing(value, expected):
    assert cc._to_rate(value) == expected


def test_normalize_card_benefits_use_parser_categories():
    card = cc.normalize_card(GOOD_CARD)
    by_cat = {b["category"]: b for b in card["benefits"]}
    # Percent rates become decimals; aliases map to parser keys; the best rate wins
    assert by_cat["shopping_online"]["rate"] == 0.05
    assert by_cat["others"]["rate"] == 0.01
    # Unknown categories and impossible rates are dropped
    assert "lounge_access" not in by_cat and "fuel" not in by_cat
    assert all(b["category"] in VALID_CATEGORIES for b in card["benefits"])
    assert by_cat["shopping_online"]["merchant_keywords"] == ["flipkart"]


def test_normalize_card_questions_match_benefits():
    card = cc.normalize_card(GOOD_CARD)
    cats = {q["maps_to_category"] for q in card["utilization_questions"]}
    ids = [q["id"] for q in card["utilization_questions"]]
    assert cats == {"shopping_online", "others"}  # grocery has no benefit
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize(
    "raw",
    [
        {"name": None, "bank": "Axis Bank", "benefits": [{"category": "others", "rate": 0.01}]},
        {"name": "Card", "bank": "Axis Bank", "benefits": [{"category": "lounge", "rate": 0.1}]},
        {"name": "Card", "bank": "Axis Bank", "benefits": []},
        ["not", "a", "dict"],
    ],
)
def test_normalize_card_rejects_unusable_output(raw):
    with pytest.raises(cc.InvalidCardData):
        cc.normalize_card(raw)


# ── crawl_url: unchanged pages and failed embeddings ───────────────────────

PAGE_HTML = (
    "<html><body><main>"
    "<p>Flipkart Axis Bank Credit Card offers 5% cashback.</p>"
    "<p>Annual fee Rs 500, waived on Rs 3.5 lakh spend.</p>"
    + "".join(f"<p>Benefit detail number {i}.</p>" for i in range(20))
    + "</main></body></html>"
)


def _browser_returning(html: str):
    page = mock.AsyncMock()
    page.content = mock.AsyncMock(return_value=html)
    context = mock.AsyncMock()
    context.new_page = mock.AsyncMock(return_value=page)
    browser = mock.AsyncMock()
    browser.new_context = mock.AsyncMock(return_value=context)
    return browser, context


def test_crawl_url_skips_gemini_when_page_unchanged():
    browser, context = _browser_returning(PAGE_HTML)
    gemini = mock.MagicMock()
    with (
        mock.patch.object(
            cc, "_find_unchanged_card", mock.AsyncMock(return_value={"_id": "axis-flipkart", "name": "F"})
        ),
        mock.patch.object(cc, "_touch_card", mock.AsyncMock()) as touch,
        mock.patch.object(cc, "_call_gemini_flash", gemini),
        mock.patch("asyncio.sleep", mock.AsyncMock()),
    ):
        result = asyncio.run(cc.crawl_url("https://www.axis.bank.in/cards/credit-card/x", browser=browser))
    assert result["success"] and result["unchanged"]
    gemini.assert_not_called()
    touch.assert_awaited_once_with("axis-flipkart")
    context.close.assert_awaited()  # browser contexts are always closed


def test_crawl_url_keeps_existing_vector_when_embedding_fails():
    browser, _ = _browser_returning(PAGE_HTML)
    upsert = mock.AsyncMock(return_value=True)
    with (
        mock.patch.object(cc, "_find_unchanged_card", mock.AsyncMock(return_value=None)),
        mock.patch.object(cc, "_call_gemini_flash", return_value=GOOD_CARD),
        mock.patch.object(cc, "_generate_embedding", return_value=([], "text")),
        mock.patch.object(cc, "_upsert_card", upsert),
        mock.patch("asyncio.sleep", mock.AsyncMock()),
    ):
        result = asyncio.run(cc.crawl_url("https://www.axis.bank.in/cards/credit-card/x", browser=browser))
    doc = upsert.await_args.args[0]
    assert result["success"] and result["slug"] == "axis-flipkart"
    assert "embedding" not in doc  # $set leaves the stored vector alone
    assert doc["content_hash"] is None  # so the next crawl retries


def test_crawl_url_reports_invalid_gemini_output():
    browser, _ = _browser_returning(PAGE_HTML)
    bad = {"name": "Card", "bank": "Axis Bank", "benefits": [{"category": "lounge", "rate": 0.1}]}
    upsert = mock.AsyncMock()
    with (
        mock.patch.object(cc, "_find_unchanged_card", mock.AsyncMock(return_value=None)),
        mock.patch.object(cc, "_call_gemini_flash", return_value=bad),
        mock.patch.object(cc, "_upsert_card", upsert),
        mock.patch("asyncio.sleep", mock.AsyncMock()),
    ):
        result = asyncio.run(cc.crawl_url("https://www.axis.bank.in/cards/credit-card/x", browser=browser))
    assert not result["success"] and "benefits" in result["error"]
    upsert.assert_not_awaited()


def test_fetch_html_retries_once_then_succeeds():
    page = mock.AsyncMock()
    page.goto = mock.AsyncMock(side_effect=[TimeoutError("slow"), None])
    page.content = mock.AsyncMock(return_value="<html></html>")
    context = mock.AsyncMock()
    context.new_page = mock.AsyncMock(return_value=page)
    browser = mock.AsyncMock()
    browser.new_context = mock.AsyncMock(return_value=context)
    with mock.patch("asyncio.sleep", mock.AsyncMock()):
        html = asyncio.run(cc._fetch_html(browser, "https://example.com"))
    assert html == "<html></html>"
    assert context.close.await_count == 2


# ── Job defaults and concurrency ────────────────────────────────────────────


def test_run_crawl_job_defaults_to_every_bank():
    crawled: list[str] = []

    async def fake_source(key):
        crawled.append(key)
        return [{"success": True, "unchanged": key == "sbi", "url": key}]

    status = mock.AsyncMock()
    with (
        mock.patch.object(cc, "crawl_source", side_effect=fake_source),
        mock.patch.object(cc, "_update_job_status", status),
    ):
        asyncio.run(cc.run_crawl_job("job-1"))
    assert crawled == list(BANK_SOURCES)
    final = status.await_args.args[1]
    assert final["cards_upserted"] == len(BANK_SOURCES) - 1
    assert final["cards_unchanged"] == 1


def test_crawl_many_dedupes_and_limits_concurrency():
    in_flight = 0
    peak = 0
    seen: list[str] = []

    async def fake_crawl(url, browser=None):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        seen.append(url)
        await asyncio.sleep(0)
        in_flight -= 1
        return {"success": True}

    urls = [f"https://example.com/{i}" for i in range(8)] + ["https://example.com/0"]
    with (
        mock.patch.object(cc, "crawl_url", side_effect=fake_crawl),
        mock.patch.object(cc.random, "uniform", return_value=0),
    ):
        results = asyncio.run(cc._crawl_many(urls, browser=None, source="test"))
    assert len(results) == 8 and sorted(seen) == sorted(set(urls))
    assert peak <= cc.CRAWL_CONCURRENCY


# ── Seeding never overwrites crawled cards ──────────────────────────────────


def test_seed_skips_cards_already_crawled():
    from db import seed

    class Cursor:
        def __init__(self, docs):
            self.docs = docs

        def __aiter__(self):
            self._it = iter(self.docs)
            return self

        async def __anext__(self):
            try:
                return next(self._it)
            except StopIteration:
                raise StopAsyncIteration from None

    col = mock.MagicMock()
    col.find = mock.MagicMock(return_value=Cursor([{"_id": "axis-flipkart"}]))
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
    assert "axis-flipkart" not in written
    assert written == {c["_id"] for c in seed.SEED_CARDS} - {"axis-flipkart"}
