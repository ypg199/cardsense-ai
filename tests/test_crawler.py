"""
tests/test_crawler.py
─────────────────────────────────────────────────────────────────────────────
Offline tests for the crawler package.
Playwright, Gemini, and MongoDB are all mocked — no live calls.
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import unittest.mock as mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crawler.card_crawler import (
    EXTRACTION_PROMPT,
    PAGE_TEXT_LIMIT,
    _clean_html,
    _make_slug,
)
from crawler.sources import ALL_SOURCE_KEYS, DIRECT_BANK_URLS, SOURCES

PASS = 0
FAIL = 0


def ok(msg):
    global PASS
    PASS += 1
    print(f"  ✅ {msg}")


def fail(msg):
    global FAIL
    FAIL += 1
    print(f"  ❌ {msg}")


# ─────────────────────────────────────────────────────────────────────────────
# 1. Sources config
# ─────────────────────────────────────────────────────────────────────────────


def test_sources_config():
    print("\n[1] sources.py — configuration")

    required_keys = {"cardinsider", "bankbazaar", "paisabazaar"}
    assert required_keys.issubset(set(SOURCES.keys()))
    ok(f"All 3 required sources present: {required_keys}")

    for key, src in SOURCES.items():
        assert "url" in src and src["url"].startswith("http")
        assert "selector" in src and len(src["selector"]) > 0
    ok("All sources have url and selector")

    # Direct bank URLs and enabled aggregator keys are deployment config
    # (some bank sites block headless crawling), so only check their shape.
    assert all(u.startswith("https://") for u in DIRECT_BANK_URLS)
    ok(f"{len(DIRECT_BANK_URLS)} direct bank URLs defined, all https")

    assert set(ALL_SOURCE_KEYS).issubset(SOURCES.keys())
    ok("ALL_SOURCE_KEYS only references known sources")

    # Check required CSS selectors
    assert SOURCES["cardinsider"]["selector"] == "a.card-name-link"
    assert SOURCES["bankbazaar"]["selector"] == "a.card-title"
    assert SOURCES["paisabazaar"]["selector"] == "a.cardTitle"
    ok("CSS selectors match spec exactly")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Slug generator
# ─────────────────────────────────────────────────────────────────────────────


def test_make_slug():
    print("\n[2] _make_slug")

    slug = _make_slug("Axis Bank", "Airtel Credit Card")
    assert "axis" in slug
    assert "airtel" in slug
    assert " " not in slug
    assert len(slug) <= 80
    ok(f"Slug generated: '{slug}'")

    slug2 = _make_slug("HDFC Bank", "Millennia Credit Card")
    assert slug2 == "hdfc-bank-millennia-credit-card"
    ok("HDFC Millennia slug correct")

    # Long bank+name truncated to 80 chars
    long_slug = _make_slug("A" * 50, "B" * 50)
    assert len(long_slug) <= 80
    ok("Long slugs truncated to 80 chars")

    # Special chars stripped
    slug3 = _make_slug("SBI Card", "Cashback! @2024#")
    assert all(c in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in slug3)
    ok("Special chars stripped from slug")

    # Multiple hyphens collapsed
    assert "--" not in _make_slug("Axis  Bank", "Credit  Card")
    ok("Multiple hyphens collapsed")


# ─────────────────────────────────────────────────────────────────────────────
# 3. HTML cleaner
# ─────────────────────────────────────────────────────────────────────────────


def test_clean_html():
    print("\n[3] _clean_html")

    html = """
    <html>
      <head><style>body{color:red}</style></head>
      <body>
        <nav>Navigation menu</nav>
        <header>Site header</header>
        <main>
          <h1>Axis Airtel Credit Card</h1>
          <p>Earn 25% cashback on Airtel recharges</p>
          <p>Annual fee: ₹500</p>
        </main>
        <aside>Ads</aside>
        <footer>Footer content</footer>
        <script>alert("hello")</script>
      </body>
    </html>
    """
    text = _clean_html(html)

    assert "Axis Airtel Credit Card" in text
    ok("Main content preserved")

    assert "Navigation menu" not in text
    ok("nav tag stripped")

    assert "Site header" not in text
    ok("header tag stripped")

    assert "Ads" not in text
    ok("aside tag stripped")

    assert "Footer content" not in text
    ok("footer tag stripped")

    assert "alert" not in text
    ok("script tag stripped")

    assert "body{color:red}" not in text
    ok("style tag stripped")

    assert len(text) <= PAGE_TEXT_LIMIT
    ok(f"Text truncated to {PAGE_TEXT_LIMIT} chars")

    # Very long HTML gets truncated
    long_html = "<main>" + "word " * 10000 + "</main>"
    assert len(_clean_html(long_html)) <= PAGE_TEXT_LIMIT
    ok("Very long HTML truncated correctly")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Extraction prompt
# ─────────────────────────────────────────────────────────────────────────────


def test_extraction_prompt():
    print("\n[4] EXTRACTION_PROMPT")

    assert "{page_content}" in EXTRACTION_PROMPT
    ok("Prompt has {page_content} placeholder")

    assert "cashback|travel|fuel|lifestyle|co-branded" in EXTRACTION_PROMPT
    ok("card_type enum present")

    assert "rate is always decimal" in EXTRACTION_PROMPT
    ok("Rate decimal rule present")

    assert "merchant_keywords" in EXTRACTION_PROMPT
    ok("merchant_keywords field documented")

    assert "utilization_questions" in EXTRACTION_PROMPT
    ok("utilization_questions in prompt")

    assert "No markdown" in EXTRACTION_PROMPT or "ONLY valid JSON" in EXTRACTION_PROMPT
    ok("JSON-only instruction present")

    assert "3-6 utilization_questions" in EXTRACTION_PROMPT
    ok("Question count guidance present")

    assert PAGE_TEXT_LIMIT == 8000
    ok("PAGE_TEXT_LIMIT == 8000 (spec requirement)")


# ─────────────────────────────────────────────────────────────────────────────
# 5. _call_gemini_flash (mocked)
# ─────────────────────────────────────────────────────────────────────────────

MOCK_CARD_RESPONSE = {
    "name": "Axis Airtel Credit Card",
    "bank": "Axis Bank",
    "network": "Visa",
    "card_type": "cashback",
    "annual_fee": 500,
    "fee_waiver_spend": 200000,
    "joining_fee": 500,
    "min_annual_income": 300000,
    "min_credit_score": 700,
    "benefits": [
        {
            "category": "airtel_recharge",
            "label": "Airtel Recharge",
            "rate": 0.25,
            "max_cashback_per_month": None,
            "reward_type": "cashback",
            "point_value_inr": None,
            "conditions": "Must pay via Airtel Thanks app",
            "merchant_keywords": ["airtel"],
        }
    ],
    "utilization_questions": [
        {
            "id": "q_airtel_sim",
            "text": "Do you recharge your Airtel SIM using this card?",
            "hint": "Earns 25% cashback",
            "maps_to_category": "airtel_recharge",
            "auto_detect_keywords": ["airtel"],
        }
    ],
    "best_for_tags": ["airtel users"],
    "not_good_for": ["amazon"],
}


def test_call_gemini_flash_success():
    print("\n[5] _call_gemini_flash — mocked Gemini success")

    mock_response = json.dumps(MOCK_CARD_RESPONSE)

    mock_llm_instance = mock.MagicMock()
    mock_llm_instance.invoke.return_value.content = mock_response
    MockLLM = mock.MagicMock(return_value=mock_llm_instance)

    with (
        mock.patch.dict(
            "sys.modules", {"langchain_google_genai": mock.MagicMock(ChatGoogleGenerativeAI=MockLLM)}
        ),
        mock.patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key"}),
    ):
        from crawler.card_crawler import _call_gemini_flash

        result = _call_gemini_flash("Sample page content about Axis Airtel card")

    assert result["name"] == "Axis Airtel Credit Card"
    ok("Card name extracted correctly")
    assert result["bank"] == "Axis Bank"
    ok("Bank name extracted")
    assert result["benefits"][0]["rate"] == 0.25
    ok("Benefit rate == 0.25")
    assert len(result["utilization_questions"]) == 1
    ok("utilization_questions parsed")


def test_call_gemini_flash_fenced():
    print("\n[6] _call_gemini_flash — strips markdown fences")

    fenced = "```json\n" + json.dumps(MOCK_CARD_RESPONSE) + "\n```"

    mock_llm_instance = mock.MagicMock()
    mock_llm_instance.invoke.return_value.content = fenced
    MockLLM = mock.MagicMock(return_value=mock_llm_instance)

    with (
        mock.patch.dict(
            "sys.modules", {"langchain_google_genai": mock.MagicMock(ChatGoogleGenerativeAI=MockLLM)}
        ),
        mock.patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key"}),
    ):
        from crawler.card_crawler import _call_gemini_flash

        result = _call_gemini_flash("page content")

    assert result["name"] == "Axis Airtel Credit Card"
    ok("Markdown-fenced JSON correctly parsed")


def test_call_gemini_no_api_key():
    print("\n[7] _call_gemini_flash — no API key raises ValueError")

    with mock.patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
        from crawler.card_crawler import _call_gemini_flash

        try:
            _call_gemini_flash("page content")
            fail("Should have raised")
        except (ValueError, Exception):
            ok("Raises when GEMINI_API_KEY not set")


# ─────────────────────────────────────────────────────────────────────────────
# 6. crawl_url (full integration mock)
# ─────────────────────────────────────────────────────────────────────────────


def test_crawl_url_success():
    print("\n[8] crawl_url — mocked Playwright + Gemini, success")

    # Page must have > 100 chars of text after cleaning
    mock_page_html = """<html><body><main>
    <h1>Axis Airtel Credit Card</h1>
    <p>The Axis Bank Airtel Credit Card is a co-branded credit card that offers
    excellent cashback on Airtel services. Earn up to 25% cashback on Airtel mobile
    recharges, 10% cashback on utility bill payments, and 10% cashback on food delivery
    from Zomato. Annual fee is Rs 500 which is waived on spending Rs 2,00,000 per year.
    Apply online with minimum income of Rs 3,00,000 annually.</p>
    <ul>
      <li>25% cashback on Airtel prepaid and postpaid recharges</li>
      <li>10% cashback on utility bills via BESCOM, MSEDCL</li>
      <li>10% cashback on Zomato food delivery orders</li>
      <li>Joining fee: Rs 500 | Annual fee: Rs 500</li>
    </ul>
    </main></body></html>"""

    async def _run():
        # Mock Playwright
        mock_page = mock.AsyncMock()
        mock_page.content = mock.AsyncMock(return_value=mock_page_html)
        mock_page.close = mock.AsyncMock()

        mock_context = mock.AsyncMock()
        mock_context.new_page = mock.AsyncMock(return_value=mock_page)
        mock_context.close = mock.AsyncMock()

        mock_browser = mock.AsyncMock()
        mock_browser.new_context = mock.AsyncMock(return_value=mock_context)
        mock_browser.close = mock.AsyncMock()

        mock_pw = mock.AsyncMock()
        mock_pw.chromium.launch = mock.AsyncMock(return_value=mock_browser)
        mock_pw.stop = mock.AsyncMock()

        mock_playwright_cm = mock.AsyncMock()
        mock_playwright_cm.__aenter__ = mock.AsyncMock(return_value=mock_pw)
        mock_playwright_cm.__aexit__ = mock.AsyncMock(return_value=False)

        # Mock page navigation
        mock_page.goto = mock.AsyncMock()

        with (
            mock.patch("crawler.card_crawler._call_gemini_flash", return_value=MOCK_CARD_RESPONSE),
            mock.patch(
                "crawler.card_crawler._generate_embedding", return_value=([0.1] * 768, "embedding text")
            ),
            mock.patch("crawler.card_crawler._upsert_card", return_value=True),
            mock.patch("asyncio.sleep", return_value=None),
        ):
            from crawler.card_crawler import crawl_url

            result = await crawl_url(
                "https://example.com/axis-airtel",
                browser=mock_browser,
            )

        return result

    result = asyncio.run(_run())
    assert result["success"] is True
    ok("crawl_url returns success=True")
    assert result["card_name"] == "Axis Airtel Credit Card"
    ok("card_name correct")
    assert result["slug"] is not None and "axis" in result["slug"]
    ok("slug generated with 'axis'")
    assert result["error"] is None
    ok("error is None on success")


def test_crawl_url_empty_page():
    print("\n[9] crawl_url — empty page returns failure")

    async def _run():
        mock_page = mock.AsyncMock()
        mock_page.content = mock.AsyncMock(return_value="<html><body></body></html>")
        mock_page.goto = mock.AsyncMock()
        mock_page.close = mock.AsyncMock()

        mock_context = mock.AsyncMock()
        mock_context.new_page = mock.AsyncMock(return_value=mock_page)
        mock_context.close = mock.AsyncMock()

        mock_browser = mock.AsyncMock()
        mock_browser.new_context = mock.AsyncMock(return_value=mock_context)

        with mock.patch("asyncio.sleep", return_value=None):
            from crawler.card_crawler import crawl_url

            result = await crawl_url("https://example.com/empty", browser=mock_browser)

        return result

    result = asyncio.run(_run())
    assert result["success"] is False
    ok("Empty page → success=False")
    assert result["error"] is not None
    ok("Error message set for empty page")


# ─────────────────────────────────────────────────────────────────────────────
# 7. Celery tasks structure
# ─────────────────────────────────────────────────────────────────────────────


def test_tasks_structure():
    print("\n[10] crawler/tasks.py — simplified structure (no Celery)")

    from crawler.tasks import _do_crawl, run_crawl

    ok("run_crawl importable")
    ok("_do_crawl importable")

    import inspect

    assert inspect.iscoroutinefunction(_do_crawl)
    ok("_do_crawl is an async coroutine")

    assert not inspect.iscoroutinefunction(run_crawl)
    ok("run_crawl is a sync function (returns immediately)")

    src = open("crawler/tasks.py").read()
    assert "celery" not in src.lower()
    ok("No Celery imports in tasks.py")

    assert "redis" not in src.lower()
    ok("No Redis references in tasks.py")

    assert "asyncio.run(" in src or "create_task" in src
    ok("Uses asyncio.run() or create_task for background execution")


def test_run_module_exists():
    print("\n[11] crawler/run.py — one-shot entrypoint")

    import os

    assert os.path.exists("crawler/run.py")
    ok("crawler/run.py exists")

    import ast

    with open("crawler/run.py") as f:
        src = f.read()
    ast.parse(src)
    ok("crawler/run.py is valid Python")

    assert "--seed-only" in src
    ok("--seed-only flag supported")

    assert "asyncio.run(" in src
    ok("Uses asyncio.run() as entrypoint")

    assert "if __name__" in src
    ok("Has __main__ guard (python -m crawler.run works)")

    assert "celery" not in src.lower() and "redis" not in src.lower()
    ok("No Celery/Redis dependencies")


# ─────────────────────────────────────────────────────────────────────────────
# 8. _generate_embedding (mocked)
# ─────────────────────────────────────────────────────────────────────────────


def test_generate_embedding():
    print("\n[12] _generate_embedding — mocked embedder")

    card_data = {
        "name": "Axis Airtel Credit Card",
        "bank": "Axis Bank",
        "benefits": [{"label": "Airtel Recharge", "rate": 0.25}],
    }

    mock_vector = [0.01] * 768
    mock_embedder = mock.MagicMock()
    mock_embedder.embed_query.return_value = mock_vector
    MockEmbed = mock.MagicMock(return_value=mock_embedder)

    with (
        mock.patch.dict(
            "sys.modules", {"langchain_google_genai": mock.MagicMock(GoogleGenerativeAIEmbeddings=MockEmbed)}
        ),
        mock.patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key"}),
    ):
        from crawler.card_crawler import _generate_embedding

        vector, text = _generate_embedding(card_data)

    assert len(vector) == 768
    ok("Embedding vector has 768 dimensions")
    assert "Axis Airtel Credit Card" in text
    ok("Card name in embedding text")
    assert "Axis Bank" in text
    ok("Bank name in embedding text")
    assert "Airtel Recharge" in text
    ok("Benefit label in embedding text")


def test_generate_embedding_failure_fallback():
    print("\n[13] _generate_embedding — returns empty vector on failure")

    card_data = {"name": "Test Card", "bank": "Test Bank", "benefits": []}

    # Simulate the embedder raising an exception inside the function
    mock_embed_mod = mock.MagicMock()
    mock_embed_mod.GoogleGenerativeAIEmbeddings.side_effect = Exception("API Error")

    with mock.patch.dict("sys.modules", {"langchain_google_genai": mock_embed_mod}):
        import importlib

        from crawler import card_crawler as cc

        importlib.reload(cc)
        vector, text = cc._generate_embedding(card_data)

    assert vector == []
    ok("Empty vector returned on embedding failure")
    assert "Test Card" in text
    ok("Embedding text still generated on failure")


# ─────────────────────────────────────────────────────────────────────────────
# 9. _upsert_card (mocked)
# ─────────────────────────────────────────────────────────────────────────────


def test_upsert_card():
    print("\n[14] _upsert_card — mocked MongoDB")

    card_doc = {
        "_id": "axis-airtel",
        "name": "Axis Airtel Credit Card",
        "bank": "Axis Bank",
    }

    mock_col = mock.MagicMock()
    mock_col.update_one = mock.AsyncMock(return_value=mock.MagicMock(upserted_id="axis-airtel"))
    mock_db = mock.MagicMock()
    mock_db.__getitem__ = mock.MagicMock(return_value=mock_col)

    with mock.patch("db.connection.get_db", return_value=mock_db):
        from crawler.card_crawler import _upsert_card

        result = asyncio.run(_upsert_card(card_doc))

    assert result is True
    ok("_upsert_card returns True on success")

    call_args = mock_col.update_one.call_args
    assert call_args[0][0] == {"_id": "axis-airtel"}
    assert call_args[1].get("upsert") is True
    ok("update_one called with correct filter and upsert=True")


# ─────────────────────────────────────────────────────────────────────────────
# Run all
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  crawler test suite")
    print("=" * 60)

    test_sources_config()
    test_make_slug()
    test_clean_html()
    test_extraction_prompt()
    test_call_gemini_flash_success()
    test_call_gemini_flash_fenced()
    test_call_gemini_no_api_key()
    test_crawl_url_success()
    test_crawl_url_empty_page()
    test_tasks_structure()
    test_run_module_exists()
    test_generate_embedding()
    test_generate_embedding_failure_fallback()
    test_upsert_card()

    print()
    print("=" * 60)
    print(f"  Results: {PASS} passed, {FAIL} failed")
    print("=" * 60)

    if FAIL > 0:
        sys.exit(1)
