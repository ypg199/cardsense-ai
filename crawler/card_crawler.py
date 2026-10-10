"""
crawler/card_crawler.py
─────────────────────────────────────────────────────────────────────────────
Card crawler — Section 8 spec implementation.

Flow per bank
─────────────
1. Open the bank's card listing page and collect product links that match
   its link_pattern, merged with the bank's known product pages.
2. Crawl the product pages a few at a time (CRAWL_CONCURRENCY).

Flow per URL
────────────
1. Load the page in headless Chromium (one retry on navigation errors).
2. Keep the <main> content, strip nav/footer/aside/script/style, drop
   repeated lines and truncate to PAGE_TEXT_LIMIT chars.
3. Skip the page if its text hash matches the stored card (no Gemini call).
4. Send to Gemini Flash with EXTRACTION_PROMPT → JSON.
5. Validate and normalise the JSON (normalize_card): categories must be ones
   the statement parser produces, rates become decimals, fees become ints.
6. Embed with gemini-embedding-001 (768-dim) and upsert to credit_cards.

Error handling
──────────────
- Never crash on a single card failure.
- Log "Upserted: {name}" on success, "Failed: {url} — {error}" on failure.
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import random
import re
from datetime import UTC, datetime
from typing import Any

from bs4 import BeautifulSoup
from dotenv import load_dotenv
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

from agents.embeddings import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL
from agents.parse_node import VALID_CATEGORIES
from db.card_keys import card_key, normalize_url

load_dotenv()
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

PAGE_TEXT_LIMIT = 15_000  # chars sent to Gemini; product details often sit below long menus
PAGE_WAIT_MIN = 1.5  # seconds after load
PAGE_WAIT_MAX = 2.0
CRAWL_CONCURRENCY = 3  # product pages fetched at once
MAX_LINKS_PER_SOURCE = 50
MAX_REASONABLE_RATE = 0.5  # no card pays more than 50% back; larger values are parse errors

VALID_NETWORKS = {
    "visa": "Visa",
    "mastercard": "Mastercard",
    "rupay": "RuPay",
    "amex": "Amex",
    "diners": "Diners",
}
VALID_CARD_TYPES = {"cashback", "travel", "fuel", "lifestyle", "co-branded"}
VALID_REWARD_TYPES = {"cashback", "points", "miles"}

# Common names Gemini uses for categories, mapped to the statement parser's keys
CATEGORY_ALIASES = {
    "online_shopping": "shopping_online",
    "ecommerce": "shopping_online",
    "e_commerce": "shopping_online",
    "offline_shopping": "shopping_offline",
    "retail": "shopping_offline",
    "flights": "travel_flights",
    "air_travel": "travel_flights",
    "airlines": "travel_flights",
    "hotels": "travel_hotels",
    "hotel": "travel_hotels",
    "utilities": "utility_bills",
    "utility": "utility_bills",
    "bill_payments": "utility_bills",
    "bills": "utility_bills",
    "food": "food_delivery",
    "groceries": "grocery",
    "supermarket": "grocery",
    "movies": "entertainment",
    "base": "others",
    "all_spends": "others",
    "all_other_spends": "others",
    "other": "others",
}


class CrawlerConfigError(RuntimeError):
    """Configuration problem (e.g. missing API key) — retrying will not help."""


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
      "category": "one of the allowed categories below",
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
- category must be exactly one of: {categories}
  Use "others" for the card's base rate on all other spends. Leave out benefits
  that fit none of these (lounge access, milestone vouchers, insurance covers).
- maps_to_category must be one of the benefit categories you returned
- If the page is not about one specific credit card (a category or listing of
  several different cards, a help, FAQ, PIN or card-blocking page), return
  "name": null
- One card sold in several variants (network, Signature/Platinum, Visa/RuPay)
  is still one card: extract it, naming the variant the page leads with
- The page title and main heading at the top usually carry the card's name
- rate is always decimal (5% = 0.05, 25% = 0.25)
- If reward is points, estimate point_value_inr (e.g. 1 point = 0.25 INR)
- merchant_keywords: lowercase words found in bank statement merchant names
- Generate 3-6 utilization_questions per card
- If field not found, use null (never omit the field)

Page content: {page_content}"""


# ─────────────────────────────────────────────────────────────────────────────
# Slug generator
# ─────────────────────────────────────────────────────────────────────────────

# card_key() lives in db/card_keys.py so the seed and duplicate checks share it
_make_slug = card_key


# ─────────────────────────────────────────────────────────────────────────────
# HTML cleaning and link discovery
# ─────────────────────────────────────────────────────────────────────────────


def _clean_html(html: str) -> str:
    """
    Return the page's readable text: the <main> element when it has real
    content, without nav/header/footer/aside/script/style, with repeated lines
    (menus rendered twice for mobile and desktop) removed.
    """
    soup = BeautifulSoup(html, "lxml")
    # The card's name often sits only in <title> or a hero <h1> inside <header>,
    # both of which the cleanup below drops, so keep them as the first lines
    top: list[str] = []
    for label, tag in (("Page title", soup.find("title")), ("Main heading", soup.find("h1"))):
        value = " ".join(tag.get_text(" ", strip=True).split()) if tag else ""
        if value:
            top.append(f"{label}: {value}")
    for tag in soup.find_all(["nav", "footer", "aside", "script", "style", "header", "noscript"]):
        tag.decompose()

    root = soup.find("main")
    if root is None or len(root.get_text(strip=True)) < 200:
        root = soup

    seen: set[str] = set()
    lines: list[str] = list(top)
    for line in root.get_text(separator="\n", strip=True).splitlines():
        key = line.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        lines.append(line.strip())
    return "\n".join(lines)[:PAGE_TEXT_LIMIT]


def _page_hash(page_text: str) -> str:
    return hashlib.sha256(page_text.encode("utf-8")).hexdigest()


_normalize_url = normalize_url


def discover_card_links(hrefs: list[str], base_url: str, link_pattern: str) -> list[str]:
    """
    Pick the product page links out of every href on a bank's listing page.
    Keeps links matching link_pattern, drops non-product pages (apply, EMI,
    FAQ...) and duplicates, and preserves page order.
    """
    from crawler.sources import NON_PRODUCT_LINK_WORDS

    pattern = re.compile(link_pattern)
    found: list[str] = []
    for href in hrefs:
        if not href or href.startswith(("javascript:", "mailto:", "tel:")):
            continue
        url = _normalize_url(href, base_url)
        slug = url.rsplit("/", 1)[-1]
        # Whole hyphen-separated words only, so "emi" doesn't reject "premium"
        slug = slug.removesuffix(".page").removesuffix(".html")
        if not pattern.match(url) or any(f"-{word}-" in f"-{slug}-" for word in NON_PRODUCT_LINK_WORDS):
            continue
        # A plural slug ("travel-credit-cards") is a category listing, not a card
        if slug.endswith("-cards"):
            continue
        if url not in found:
            found.append(url)
    return found


# ─────────────────────────────────────────────────────────────────────────────
# Gemini LLM call
# ─────────────────────────────────────────────────────────────────────────────


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_not_exception_type(CrawlerConfigError),
    reraise=True,
)
def _call_gemini_flash(page_content: str) -> dict:
    """
    Call Gemini Flash to extract card data from page text.
    Returns a parsed dict or raises on failure. Synchronous: call it through
    asyncio.to_thread from async code.
    """
    from langchain_google_genai import ChatGoogleGenerativeAI

    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise CrawlerConfigError("GEMINI_API_KEY not set")

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=api_key,
        temperature=0,
    )
    prompt = EXTRACTION_PROMPT.format(
        page_content=page_content[:PAGE_TEXT_LIMIT],
        categories=", ".join(sorted(VALID_CATEGORIES)),
    )
    response = llm.invoke(prompt)
    raw = response.content

    # Strip markdown fences
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)

    return json.loads(cleaned)


# ─────────────────────────────────────────────────────────────────────────────
# Validation and normalisation of Gemini output
# ─────────────────────────────────────────────────────────────────────────────


class InvalidCardData(ValueError):
    """Gemini's output does not describe a usable card."""


def _to_amount(value: Any) -> int | None:
    """Parse "₹500 + GST", "Rs. 2,00,000", "Nil", 500 or None into whole rupees."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return int(value) if value >= 0 else None
    text = str(value).lower()
    match = re.search(r"\d[\d,]*(\.\d+)?", text)
    if match:
        return int(float(match.group(0).replace(",", "")))
    if any(word in text for word in ("nil", "free", "zero")):
        return 0
    return None


def _to_rate(value: Any) -> float | None:
    """Turn 0.05, 5, "5%" or "5" into 0.05. Returns None for nonsense."""
    if value is None or isinstance(value, bool):
        return None
    try:
        rate = float(str(value).replace("%", "").strip())
    except ValueError:
        return None
    if rate >= 1:  # given as a percentage
        rate /= 100
    if rate <= 0 or rate > MAX_REASONABLE_RATE:
        return None
    return round(rate, 4)


def _to_category(value: Any) -> str | None:
    key = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")
    key = CATEGORY_ALIASES.get(key, key)
    return key if key in VALID_CATEGORIES else None


def _to_str_list(value: Any, limit: int = 20) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()][:limit]


def normalize_card(raw: dict) -> dict:
    """
    Validate Gemini's card JSON and coerce it into the shape the cashback and
    compare nodes rely on. Raises InvalidCardData when the page did not yield
    a single card with at least one usable benefit.
    """
    if not isinstance(raw, dict):
        raise InvalidCardData("Gemini did not return a JSON object")

    name = str(raw.get("name") or "").strip()
    bank = str(raw.get("bank") or "").strip()
    if not name or not bank:
        raise InvalidCardData("Gemini returned empty name or bank")

    benefits: dict[str, dict] = {}
    dropped: list[str] = []
    for b in raw.get("benefits") or []:
        if not isinstance(b, dict):
            continue
        category = _to_category(b.get("category"))
        rate = _to_rate(b.get("rate"))
        if category is None or rate is None:
            dropped.append(str(b.get("category")))
            continue
        reward_type = str(b.get("reward_type") or "cashback").lower()
        benefit = {
            "category": category,
            "label": str(b.get("label") or category.replace("_", " ").title()).strip(),
            "rate": rate,
            "max_cashback_per_month": _to_amount(b.get("max_cashback_per_month")),
            "reward_type": reward_type if reward_type in VALID_REWARD_TYPES else "cashback",
            "point_value_inr": b.get("point_value_inr"),
            "conditions": b.get("conditions"),
            "merchant_keywords": [k.lower() for k in _to_str_list(b.get("merchant_keywords"))],
        }
        # One benefit per category: the cashback node indexes them by category
        if category not in benefits or rate > benefits[category]["rate"]:
            benefits[category] = benefit
    if dropped:
        logger.info("  Dropped benefits with unknown category or rate: %s", ", ".join(dropped))
    if not benefits:
        raise InvalidCardData("No benefits with a known category and a valid rate")

    questions: list[dict] = []
    seen_ids: set[str] = set()
    for q in raw.get("utilization_questions") or []:
        if not isinstance(q, dict):
            continue
        category = _to_category(q.get("maps_to_category"))
        text = str(q.get("text") or "").strip()
        if category not in benefits or not text:
            continue
        qid = re.sub(r"[^a-z0-9_]+", "_", str(q.get("id") or f"q_{category}").lower())
        while qid in seen_ids:
            qid += "_x"
        seen_ids.add(qid)
        questions.append(
            {
                "id": qid,
                "text": text,
                "hint": str(q.get("hint") or "").strip(),
                "maps_to_category": category,
                "auto_detect_keywords": [k.lower() for k in _to_str_list(q.get("auto_detect_keywords"))],
            }
        )

    network = VALID_NETWORKS.get(str(raw.get("network") or "").strip().lower())
    card_type = str(raw.get("card_type") or "").strip().lower()

    return {
        "name": name,
        "bank": bank,
        "network": network,
        "card_type": card_type if card_type in VALID_CARD_TYPES else "cashback",
        "annual_fee": _to_amount(raw.get("annual_fee")) or 0,
        "fee_waiver_spend": _to_amount(raw.get("fee_waiver_spend")),
        "joining_fee": _to_amount(raw.get("joining_fee")) or 0,
        "min_annual_income": _to_amount(raw.get("min_annual_income")),
        "min_credit_score": _to_amount(raw.get("min_credit_score")),
        "benefits": list(benefits.values()),
        "utilization_questions": questions,
        "best_for_tags": _to_str_list(raw.get("best_for_tags"), limit=8),
        "not_good_for": _to_str_list(raw.get("not_good_for"), limit=8),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Embedding
# ─────────────────────────────────────────────────────────────────────────────


def _generate_embedding(card_data: dict) -> tuple[list[float], str]:
    """
    Generate a 768-dim gemini-embedding-001 embedding for the card.
    Embedding text: "Card: {name} by {bank}. Benefits: {benefit_labels}"
    Returns (embedding_vector, embedding_text); the vector is empty on failure.
    """
    benefit_labels = ", ".join(
        f"{b.get('label', '')} {round(b.get('rate', 0) * 100, 1):g}%"
        for b in card_data.get("benefits", [])[:6]
        if b.get("rate", 0) > 0
    )
    embedding_text = (
        f"Card: {card_data.get('name', '')} by {card_data.get('bank', '')}. Benefits: {benefit_labels}"
    )

    try:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        embedder = GoogleGenerativeAIEmbeddings(
            model=EMBEDDING_MODEL,
            google_api_key=os.getenv("GEMINI_API_KEY", ""),
        )
        vector = embedder.embed_query(embedding_text, output_dimensionality=EMBEDDING_DIMENSIONS)
        return vector, embedding_text
    except Exception as exc:
        logger.warning("Embedding failed: %s", exc)
        return [], embedding_text


# ─────────────────────────────────────────────────────────────────────────────
# MongoDB access
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


def _url_variants(url: str) -> list[str]:
    """The URL as given plus its normalised form, with and without a trailing slash."""
    clean = _normalize_url(url, url)
    return list(dict.fromkeys([url, clean, clean + "/"]))


async def _find_stored_card(url: str) -> dict | None:
    """
    Return the stored card crawled from this URL, if any. Its _id is reused
    when the page is re-crawled, so a card whose extracted name changes
    (or that an older crawler stored under another id) is updated in place
    rather than saved a second time.
    """
    try:
        from db.connection import get_db

        db = get_db()
        return await db["credit_cards"].find_one(
            {"source_url": {"$in": _url_variants(url)}},
            {"_id": 1, "name": 1, "content_hash": 1},
            sort=[("last_crawled", -1)],
        )
    except Exception as exc:
        logger.warning("Could not check stored card for %s: %s", url, exc)
        return None


async def _touch_card(card_id: str) -> None:
    """Record that an unchanged card was checked."""
    try:
        from db.connection import get_db

        db = get_db()
        await db["credit_cards"].update_one(
            {"_id": card_id}, {"$set": {"last_crawled": datetime.now(UTC).isoformat()}}
        )
    except Exception as exc:
        logger.warning("Could not update last_crawled for %s: %s", card_id, exc)


# ─────────────────────────────────────────────────────────────────────────────
# Page fetching
# ─────────────────────────────────────────────────────────────────────────────


async def _scroll_to_bottom(page, rounds: int = 8) -> None:
    """Scroll in steps so listings that load cards lazily render all of them."""
    for _ in range(rounds):
        before = await page.evaluate("document.body.scrollHeight")
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(0.8)
        if await page.evaluate("document.body.scrollHeight") == before:
            break


async def _fetch_html(browser, url: str, attempts: int = 2, scroll: bool = False) -> str:
    """Load a page and return its HTML, retrying once on navigation errors."""
    last_exc: Exception | None = None
    for attempt in range(attempts):
        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1280, "height": 800},
            extra_http_headers={"Accept-Language": "en-IN,en;q=0.9"},
        )
        try:
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            # Give client-side rendering a moment
            await asyncio.sleep(random.uniform(PAGE_WAIT_MIN, PAGE_WAIT_MAX))
            if scroll:
                await _scroll_to_bottom(page)
            return await page.content()
        except Exception as exc:
            last_exc = exc
            if attempt + 1 < attempts:
                await asyncio.sleep(2 * (attempt + 1))
        finally:
            try:
                await context.close()
            except Exception:
                pass
    raise last_exc or RuntimeError(f"Could not load {url}")


# ─────────────────────────────────────────────────────────────────────────────
# Core per-URL extraction function
# ─────────────────────────────────────────────────────────────────────────────


def _result(
    success: bool, name=None, slug=None, error=None, unchanged: bool = False, skipped: bool = False
) -> dict[str, Any]:
    return {
        "success": success,
        "card_name": name,
        "slug": slug,
        "error": error,
        "unchanged": unchanged,
        "skipped": skipped,
    }


async def crawl_url(url: str, browser=None) -> dict[str, Any]:
    """
    Crawl a single card page URL.
    Returns {"success": bool, "card_name": str, "slug": str, "error": str|None, "unchanged": bool}
    """
    pw = None
    own_browser = browser is None
    try:
        if own_browser:
            from playwright.async_api import async_playwright

            pw = await async_playwright().start()
            browser = await pw.chromium.launch(headless=True)
        html = await _fetch_html(browser, url)
    except Exception as exc:
        logger.error("Failed: %s — %s", url, exc)
        return _result(False, error=f"Page load failed: {exc}")
    finally:
        if own_browser:
            try:
                await browser.close()
                await pw.stop()
            except Exception:
                pass

    page_text = _clean_html(html)
    if len(page_text.strip()) < 100:
        return _result(False, error=f"Page text too short ({len(page_text)} chars) — likely blocked")

    # Skip Gemini when the page hasn't changed since the last crawl
    content_hash = _page_hash(page_text)
    stored = await _find_stored_card(url)
    if stored and stored.get("content_hash") == content_hash:
        await _touch_card(stored["_id"])
        logger.info("Unchanged: %s (%s)", stored.get("name"), stored["_id"])
        return _result(True, stored.get("name"), stored["_id"], unchanged=True)

    try:
        raw = await asyncio.to_thread(_call_gemini_flash, page_text)
    except Exception as exc:
        logger.error("Failed: %s — Gemini extraction error: %s", url, exc)
        return _result(False, error=f"Gemini extraction failed: {exc}")

    if isinstance(raw, dict) and not str(raw.get("name") or "").strip():
        # The model judged it a category, help or FAQ page: not a failure
        logger.info("Skipped: %s — not a single card's page", url)
        return _result(False, error="Not a card page", skipped=True)

    try:
        card = normalize_card(raw)
    except InvalidCardData as exc:
        logger.error("Failed: %s — %s", url, exc)
        return _result(False, error=str(exc))

    # Keep the id of the card already stored from this page, so a re-crawl
    # never leaves the old record behind as a duplicate
    slug = stored["_id"] if stored else _make_slug(card["bank"], card["name"])
    embedding, embedding_text = await asyncio.to_thread(_generate_embedding, card)

    doc = {
        "_id": slug,
        **card,
        "source_url": url,
        "content_hash": content_hash,
        "last_crawled": datetime.now(UTC).isoformat(),
        "embedding_text": embedding_text,
    }
    if embedding:
        doc["embedding"] = embedding
    else:
        # Keep any existing vector; a null hash makes the next crawl retry
        doc["content_hash"] = None

    if await _upsert_card(doc):
        logger.info("Upserted: %s (%s)", card["name"], slug)
        return _result(True, card["name"], slug)
    return _result(False, card["name"], slug, error="DB upsert failed")


# ─────────────────────────────────────────────────────────────────────────────
# Crawling many pages
# ─────────────────────────────────────────────────────────────────────────────


async def _crawl_many(urls: list[str], browser, source: str) -> list[dict]:
    """Crawl URLs (deduplicated) with at most CRAWL_CONCURRENCY pages in flight."""
    semaphore = asyncio.Semaphore(CRAWL_CONCURRENCY)

    async def one(url: str) -> dict:
        async with semaphore:
            result = await crawl_url(url, browser=browser)
            # Be polite: brief pause before the next page from this worker
            await asyncio.sleep(random.uniform(0.8, 1.5))
            return {**result, "url": url, "source": source}

    unique = list(dict.fromkeys(urls))
    return list(await asyncio.gather(*(one(u) for u in unique)))


async def _listing_hrefs(browser, listing_url: str, selector: str = "a[href]") -> list[str]:
    """Return the hrefs of all links matching selector on a listing page."""
    html = await _fetch_html(browser, listing_url, scroll=True)
    soup = BeautifulSoup(html, "lxml")
    return [a.get("href", "") for a in soup.select(selector)]


async def discover_bank_cards(browser, source_key: str) -> list[str]:
    """Product page URLs for a bank: discovered links first, then known pages."""
    from crawler.sources import BANK_SOURCES

    source = BANK_SOURCES[source_key]
    discovered: list[str] = []
    try:
        hrefs = await _listing_hrefs(browser, source["listing_url"])
        discovered = discover_card_links(hrefs, source["listing_url"], source["link_pattern"])
    except Exception as exc:
        logger.warning("Listing page failed for %s: %s", source_key, exc)
    logger.info("  %s: discovered %d card links on the listing page", source_key, len(discovered))
    urls = list(dict.fromkeys(discovered + source["card_urls"]))
    return urls[:MAX_LINKS_PER_SOURCE]


async def crawl_source(source_key: str) -> list[dict]:
    """
    Crawl a bank or aggregator source: discover card links, then crawl each
    card page. Returns list of per-URL result dicts.
    """
    from crawler.sources import BANK_SOURCES, SOURCES

    if source_key not in BANK_SOURCES and source_key not in SOURCES:
        logger.error("Unknown source key: %s", source_key)
        return []

    from playwright.async_api import async_playwright

    results: list[dict] = []
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                if source_key in BANK_SOURCES:
                    urls = await discover_bank_cards(browser, source_key)
                else:
                    source = SOURCES[source_key]
                    logger.info("Starting source crawl: %s → %s", source_key, source["url"])
                    hrefs = await _listing_hrefs(browser, source["url"], source["selector"])
                    urls = [_normalize_url(h, source["url"]) for h in hrefs if h][:MAX_LINKS_PER_SOURCE]
                    logger.info("  Found %d card links on %s", len(urls), source_key)
                results = await _crawl_many(urls, browser, source_key)
            finally:
                await browser.close()
    except Exception as exc:
        logger.error("Source crawl failed (%s): %s", source_key, exc)

    return results


async def crawl_urls(urls: list[str]) -> list[dict]:
    """Crawl a list of direct URLs. Used for admin one-off crawls."""
    from playwright.async_api import async_playwright

    results: list[dict] = []
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                results = await _crawl_many(urls, browser, "direct")
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
    Full crawl job, updating its status in MongoDB throughout.

    With no arguments it crawls every bank source (listing discovery plus known
    product pages). Passing direct_urls crawls exactly those pages instead.
    """
    from crawler.sources import BANK_SOURCE_KEYS

    await _update_job_status(job_id, {"status": "running"})

    if sources is None and direct_urls is None:
        sources = BANK_SOURCE_KEYS

    all_results: list[dict] = []
    for key in sources or []:
        try:
            all_results.extend(await crawl_source(key))
        except Exception as exc:
            logger.error("Source %s failed: %s", key, exc)

    if direct_urls:
        all_results.extend(await crawl_urls(direct_urls))

    upserted = sum(1 for r in all_results if r.get("success") and not r.get("unchanged"))
    unchanged = sum(1 for r in all_results if r.get("unchanged"))
    skipped = [r for r in all_results if r.get("skipped")]
    failures = [r for r in all_results if not r.get("success") and not r.get("skipped")]
    failed = len(failures)
    errors = [f"{r.get('url', '?')}: {r.get('error', '?')}" for r in failures][:20]

    await _update_job_status(
        job_id,
        {
            "status": "done",
            "cards_upserted": upserted,
            "cards_unchanged": unchanged,
            "cards_failed": failed,
            "pages_skipped": len(skipped),
            "skipped_urls": [r.get("url", "?") for r in skipped][:50],
            "errors": errors,
            "finished_at": datetime.now(UTC).isoformat(),
        },
    )

    logger.info(
        "Crawl job %s complete — upserted=%d unchanged=%d failed=%d skipped=%d (not card pages)",
        job_id,
        upserted,
        unchanged,
        failed,
        len(skipped),
    )
