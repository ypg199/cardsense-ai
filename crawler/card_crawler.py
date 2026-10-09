"""
crawler/card_crawler.py
─────────────────────────────────────────────────────────────────────────────
Card crawler — Section 8 spec implementation.

Flow per URL
────────────
1. Launch Playwright headless Chromium with realistic user-agent.
2. Navigate to the page, wait 1.5-2s for JS rendering.
3. Strip nav/footer/aside/script/style tags with BeautifulSoup.
4. Truncate cleaned text to 8 000 chars.
5. Send to Gemini Flash with EXTRACTION_PROMPT → receive JSON.
6. Generate card slug and text-embedding-004 embedding.
7. Upsert to MongoDB credit_cards collection.

Error handling
──────────────
- Never crash on a single card failure.
- Log "Upserted: {name}" on success, "Failed: {url} — {error}" on failure.
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
from datetime import UTC, datetime
from typing import Any

from bs4 import BeautifulSoup
from dotenv import load_dotenv
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

load_dotenv()
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

PAGE_TEXT_LIMIT = 8_000  # chars sent to Gemini (spec: 8000)
PAGE_WAIT_MIN = 1.5  # seconds after load
PAGE_WAIT_MAX = 2.0

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
]

# ── Exact extraction prompt — Section 8 ──────────────────────────────────────
EXTRACTION_PROMPT = """\
You are a credit card data extractor for Indian credit cards.
Given the text content of a credit card page, extract ALL benefit and cashback info.
Return ONLY valid JSON in this EXACT format. No markdown. No explanation.

{{
  "name": "Full Card Name",
  "bank": "Bank Name",
  "network": "Visa|Mastercard|RuPay|Amex",
  "card_type": "cashback|travel|fuel|lifestyle|co-branded",
  "annual_fee": 500,
  "fee_waiver_spend": 50000,
  "joining_fee": 500,
  "min_annual_income": 300000,
  "min_credit_score": 700,
  "benefits": [
    {{
      "category": "snake_case_key",
      "label": "Human readable label",
      "rate": 0.05,
      "max_cashback_per_month": null,
      "reward_type": "cashback|points|miles",
      "point_value_inr": null,
      "conditions": "string or null",
      "merchant_keywords": ["keyword1"]
    }}
  ],
  "utilization_questions": [
    {{
      "id": "q_unique_id",
      "text": "Do you ... using this card?",
      "hint": "You can earn X% cashback",
      "maps_to_category": "category_key",
      "auto_detect_keywords": ["keyword"]
    }}
  ],
  "best_for_tags": ["short phrase"],
  "not_good_for": ["short phrase"]
}}

RULES:
- rate is always decimal (5% = 0.05, 25% = 0.25)
- If reward is points, estimate point_value_inr (e.g. 1 point = 0.25 INR)
- merchant_keywords: lowercase words found in bank statement merchant names
- Generate 3-6 utilization_questions per card
- If field not found, use null (never omit the field)

Page content: {page_content}"""


# ─────────────────────────────────────────────────────────────────────────────
# Slug generator
# ─────────────────────────────────────────────────────────────────────────────


def _make_slug(bank: str, name: str) -> str:
    """
    Generate URL-safe slug: bank-name. Truncated to 80 chars.
    Example: "axis-airtel-credit-card"
    """
    raw = f"{bank.lower()}-{name.lower()}"
    slug = re.sub(r"[^a-z0-9-]", "-", raw)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:80]


# ─────────────────────────────────────────────────────────────────────────────
# HTML cleaning
# ─────────────────────────────────────────────────────────────────────────────


def _clean_html(html: str) -> str:
    """Strip nav/footer/aside/script/style and return plain text."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(["nav", "footer", "aside", "script", "style", "header"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    # Collapse excessive whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:PAGE_TEXT_LIMIT]


# ─────────────────────────────────────────────────────────────────────────────
# Gemini LLM call
# ─────────────────────────────────────────────────────────────────────────────


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
def _call_gemini_flash(page_content: str) -> dict:
    """
    Call Gemini Flash to extract card data from page text.
    Returns a parsed dict or raises on failure.
    """
    from langchain_google_genai import ChatGoogleGenerativeAI

    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set")

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=api_key,
        temperature=0,
    )
    prompt = EXTRACTION_PROMPT.format(page_content=page_content[:PAGE_TEXT_LIMIT])
    response = llm.invoke(prompt)
    raw = response.content

    # Strip markdown fences
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)

    return json.loads(cleaned)


# ─────────────────────────────────────────────────────────────────────────────
# Embedding
# ─────────────────────────────────────────────────────────────────────────────


def _generate_embedding(card_data: dict) -> tuple[list[float], str]:
    """
    Generate 768-dim text-embedding-004 embedding for the card.
    Embedding text: "Card: {name} by {bank}. Benefits: {benefit_labels}"
    Returns (embedding_vector, embedding_text).
    """
    benefit_labels = ", ".join(
        f"{b.get('label', '')} {int(b.get('rate', 0) * 100)}%"
        for b in card_data.get("benefits", [])[:6]
        if b.get("rate", 0) > 0
    )
    embedding_text = (
        f"Card: {card_data.get('name', '')} by {card_data.get('bank', '')}. Benefits: {benefit_labels}"
    )

    try:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        embedder = GoogleGenerativeAIEmbeddings(
            model="models/text-embedding-004",
            google_api_key=os.getenv("GEMINI_API_KEY", ""),
        )
        vector = embedder.embed_query(embedding_text)
        return vector, embedding_text
    except Exception as exc:
        logger.warning("Embedding failed: %s — storing empty vector", exc)
        return [], embedding_text


# ─────────────────────────────────────────────────────────────────────────────
# MongoDB upsert
# ─────────────────────────────────────────────────────────────────────────────


async def _upsert_card(card_doc: dict) -> bool:
    """Upsert a card document to MongoDB. Returns True on success."""
    try:
        from db.connection import get_db

        db = get_db()
        await db["credit_cards"].update_one(
            {"_id": card_doc["_id"]},
            {"$set": card_doc},
            upsert=True,
        )
        return True
    except Exception as exc:
        logger.error("DB upsert failed for '%s': %s", card_doc.get("_id"), exc)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Core per-URL extraction function
# ─────────────────────────────────────────────────────────────────────────────


async def crawl_url(url: str, browser=None) -> dict[str, Any]:
    """
    Crawl a single card page URL.
    Returns {"success": bool, "card_name": str, "slug": str, "error": str|None}
    """
    page = None
    own_browser = browser is None

    try:
        # Launch browser if not provided
        if own_browser:
            from playwright.async_api import async_playwright

            pw = await async_playwright().start()
            browser = await pw.chromium.launch(headless=True)

        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1280, "height": 800},
            extra_http_headers={"Accept-Language": "en-IN,en;q=0.9"},
        )
        page = await context.new_page()

        # Navigate with timeout
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)

        # Wait for JS rendering (1.5-2s as per spec)
        await asyncio.sleep(random.uniform(PAGE_WAIT_MIN, PAGE_WAIT_MAX))

        html = await page.content()

    except Exception as exc:
        logger.error("Failed: %s — %s", url, exc)
        return {"success": False, "card_name": None, "slug": None, "error": str(exc)}
    finally:
        if page:
            try:
                await page.close()
            except Exception:
                pass
        if own_browser:
            try:
                await browser.close()
                await pw.stop()
            except Exception:
                pass

    # Clean HTML
    page_text = _clean_html(html)
    if len(page_text.strip()) < 100:
        return {
            "success": False,
            "card_name": None,
            "slug": None,
            "error": f"Page text too short ({len(page_text)} chars) — likely blocked",
        }

    # Gemini extraction
    try:
        card_data = _call_gemini_flash(page_text)
    except Exception as exc:
        logger.error("Failed: %s — Gemini extraction error: %s", url, exc)
        return {"success": False, "card_name": None, "slug": None, "error": str(exc)}

    # Validate minimal required fields
    name = card_data.get("name", "").strip()
    bank = card_data.get("bank", "").strip()
    if not name or not bank:
        return {
            "success": False,
            "card_name": None,
            "slug": None,
            "error": "Gemini returned empty name or bank",
        }

    # Generate slug
    slug = _make_slug(bank, name)

    # Generate embedding
    embedding, embedding_text = _generate_embedding(card_data)

    # Build final document
    doc = {
        "_id": slug,
        "name": name,
        "bank": bank,
        "network": card_data.get("network", "Visa"),
        "card_type": card_data.get("card_type", "cashback"),
        "annual_fee": int(card_data.get("annual_fee") or 0),
        "fee_waiver_spend": card_data.get("fee_waiver_spend"),
        "joining_fee": int(card_data.get("joining_fee") or 0),
        "min_annual_income": card_data.get("min_annual_income"),
        "min_credit_score": card_data.get("min_credit_score"),
        "benefits": card_data.get("benefits", []),
        "utilization_questions": card_data.get("utilization_questions", []),
        "best_for_tags": card_data.get("best_for_tags", []),
        "not_good_for": card_data.get("not_good_for", []),
        "source_url": url,
        "last_crawled": datetime.now(UTC).isoformat(),
        "embedding": embedding,
        "embedding_text": embedding_text,
    }

    # Upsert to DB
    ok = await _upsert_card(doc)
    if ok:
        logger.info("Upserted: %s (%s)", name, slug)
        return {"success": True, "card_name": name, "slug": slug, "error": None}
    else:
        return {"success": False, "card_name": name, "slug": slug, "error": "DB upsert failed"}


# ─────────────────────────────────────────────────────────────────────────────
# Source crawler — discovers card links then crawls each
# ─────────────────────────────────────────────────────────────────────────────


async def crawl_source(source_key: str) -> list[dict]:
    """
    Crawl an aggregator source: discover card links, then crawl each card page.
    Returns list of per-URL result dicts.
    """
    from crawler.sources import SOURCES

    source = SOURCES.get(source_key)
    if not source:
        logger.error("Unknown source key: %s", source_key)
        return []

    logger.info("Starting source crawl: %s → %s", source_key, source["url"])

    from playwright.async_api import async_playwright

    results = []
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                # Discover card links from index page
                context = await browser.new_context(
                    user_agent=random.choice(USER_AGENTS),
                    viewport={"width": 1280, "height": 800},
                )
                page = await context.new_page()
                await page.goto(source["url"], wait_until="domcontentloaded", timeout=30_000)
                await asyncio.sleep(random.uniform(PAGE_WAIT_MIN, PAGE_WAIT_MAX))

                # Extract all card links
                links = await page.eval_on_selector_all(
                    source["selector"],
                    "els => els.map(e => e.href).filter(Boolean)",
                )
                await page.close()
                await context.close()

                logger.info("  Found %d card links on %s", len(links), source_key)

                # Crawl each card (cap at 50 per source to avoid overloading)
                for url in links[:50]:
                    result = await crawl_url(url, browser=browser)
                    results.append({**result, "url": url, "source": source_key})
                    # Brief pause between pages
                    await asyncio.sleep(random.uniform(0.8, 1.5))

            finally:
                await browser.close()

    except Exception as exc:
        logger.error("Source crawl failed (%s): %s", source_key, exc)

    return results


async def crawl_urls(urls: list[str]) -> list[dict]:
    """Crawl a list of direct URLs. Used for bank-direct and admin one-off crawls."""
    results = []
    from playwright.async_api import async_playwright

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                for url in urls:
                    result = await crawl_url(url, browser=browser)
                    results.append({**result, "url": url, "source": "direct"})
                    await asyncio.sleep(random.uniform(0.8, 1.5))
            finally:
                await browser.close()
    except Exception as exc:
        logger.error("Direct URL crawl failed: %s", exc)
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Job status updater (called from the crawl task)
# ─────────────────────────────────────────────────────────────────────────────


async def _update_job_status(job_id: str, patch: dict) -> None:
    try:
        from db.connection import get_db

        db = get_db()
        await db["crawl_jobs"].update_one({"_id": job_id}, {"$set": patch})
    except Exception as exc:
        logger.warning("Failed to update crawl job %s: %s", job_id, exc)


async def run_crawl_job(
    job_id: str,
    sources: list[str] | None = None,
    direct_urls: list[str] | None = None,
) -> None:
    """
    Full crawl job: runs source crawls + direct URL crawls,
    updates job status in MongoDB throughout.
    """

    from crawler.sources import ALL_SOURCE_KEYS, DIRECT_BANK_URLS

    await _update_job_status(job_id, {"status": "running"})

    source_keys = sources or ALL_SOURCE_KEYS
    urls = direct_urls or DIRECT_BANK_URLS

    all_results = []

    # Crawl sources
    for key in source_keys:
        try:
            results = await crawl_source(key)
            all_results.extend(results)
        except Exception as exc:
            logger.error("Source %s failed: %s", key, exc)

    # Crawl direct URLs
    try:
        results = await crawl_urls(urls)
        all_results.extend(results)
    except Exception as exc:
        logger.error("Direct URL crawl failed: %s", exc)

    upserted = sum(1 for r in all_results if r.get("success"))
    failed = sum(1 for r in all_results if not r.get("success"))
    errors = [f"{r.get('url', '?')}: {r.get('error', '?')}" for r in all_results if not r.get("success")][:20]

    await _update_job_status(
        job_id,
        {
            "status": "done",
            "cards_upserted": upserted,
            "cards_failed": failed,
            "errors": errors,
            "finished_at": datetime.now(UTC).isoformat(),
        },
    )

    logger.info("Crawl job %s complete — upserted=%d failed=%d", job_id, upserted, failed)
