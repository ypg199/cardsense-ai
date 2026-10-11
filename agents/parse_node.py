"""
agents/parse_node.py
─────────────────────────────────────────────────────────────────────────────
Node 2: parse_transactions_node

Responsibilities
────────────────
1. Take the extracted pdf_text for the current card.
2. Send (up to 10 000 chars) to Gemini (agents.llm.GEMINI_MODEL) with the exact prompt
   defined in Section 11 (TRANSACTION_PARSE_PROMPT).
3. Parse the returned JSON array into a list of Transaction dicts.
4. Attach the source month label to each transaction.
5. Compute total_spend (sum of all debit amounts).
6. Write results back to AnalysisState.

State fields read
─────────────────
  cards[current_card_idx].pdf_text
  cards[current_card_idx].months
  current_card_idx

State fields written
────────────────────
  cards[current_card_idx].transactions    – list[Transaction]
  cards[current_card_idx].total_spend     – float
  cards[current_card_idx].status          – "questioning"
  status                                  – "questioning"
  ui_action                               – "show_loading"
  error                                   – set on fatal failure
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from copy import deepcopy
from typing import Any

from dotenv import load_dotenv
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

from agents.llm import GEMINI_MODEL
from agents.state import AnalysisState, CardState, Transaction

load_dotenv()
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

PDF_TEXT_CHAR_LIMIT = 10_000  # Max chars per Gemini request; longer statements are sent in parts

VALID_CATEGORIES = frozenset(
    {
        "airtel_recharge",
        "utility_bills",
        "food_delivery",
        "grocery",
        "shopping_online",
        "shopping_offline",
        "travel_flights",
        "travel_hotels",
        "fuel",
        "entertainment",
        "emi",
        "insurance",
        "healthcare",
        "education",
        "rent",
        "others",
    }
)

VALID_TRANSACTION_TYPES = frozenset({"debit", "credit", "refund"})

# ── Exact prompt from Section 11 ─────────────────────────────────────────────
TRANSACTION_PARSE_PROMPT = """\
You are a bank statement parser for Indian credit card statements.

Extract EVERY debit transaction. Return ONLY a JSON array. No markdown.

For each transaction:
  date: YYYY-MM-DD
  merchant: cleaned name (remove transaction IDs, extra chars)
  amount: positive float (debit amount)
  transaction_type: 'debit' | 'credit' | 'refund'
  category: one of [airtel_recharge, utility_bills, food_delivery, grocery,
    shopping_online, shopping_offline, travel_flights, travel_hotels, fuel,
    entertainment, emi, insurance, healthcare, education, rent, others]

Auto-rules:
  'zomato','swiggy','eatsure' → food_delivery
  'airtel' → airtel_recharge
  'amazon' → shopping_online
  'flipkart','myntra' → shopping_online
  'irctc','indigo','spicejet','makemytrip' → travel_flights
  'oyo','goibibo hotel' → travel_hotels
  'bescom','msedcl','mahanagar gas' → utility_bills
  'bigbasket','blinkit','zepto' → grocery
  EMI deductions → emi
  Cashback credit lines → transaction_type='credit', category='others'

Only rows from the statement's transaction list count: each one has its own
date and amount on the row. Ignore every other table or figure, such as a
schedule of charges or fee table (card names with annual or renewal fees),
interest rates, reward point summaries, offers, credit limits and the amount
due. Never invent a date. If this text has no transaction rows, return [].

Statement text (may be one part of a longer statement):
{pdf_text}"""


# ─────────────────────────────────────────────────────────────────────────────
# Gemini client (lazy-initialised so tests can mock before import)
# ─────────────────────────────────────────────────────────────────────────────


class GeminiNotConfiguredError(RuntimeError):
    """Raised when GEMINI_API_KEY is missing, so parsing can't run at all."""


class GeminiUnavailableError(RuntimeError):
    """Raised when every Gemini call for a statement failed (bad key, quota, outage)."""


def _get_llm():
    """Return a ChatGoogleGenerativeAI instance for GEMINI_MODEL."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise GeminiNotConfiguredError("GEMINI_API_KEY is not set")
    return ChatGoogleGenerativeAI(
        model=GEMINI_MODEL,
        google_api_key=api_key,
        temperature=0,
        # JSON mode: the model must return syntactically valid JSON
        response_mime_type="application/json",
    )


# ─────────────────────────────────────────────────────────────────────────────
# JSON cleaning helpers (Section 14 pitfall)
# ─────────────────────────────────────────────────────────────────────────────


def _clean_gemini_json(raw: str) -> str:
    """
    Strip markdown fences that Gemini sometimes wraps JSON in.
    Spec Section 14:
        raw.replace('```json','').replace('```','').strip()
    """
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    # Also remove any leading/trailing text before the first '[' or after the last ']'
    match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if match:
        return match.group(0)
    return cleaned


# ─────────────────────────────────────────────────────────────────────────────
# Transaction validation / normalisation
# ─────────────────────────────────────────────────────────────────────────────


def _normalise_transaction(raw: dict, month_fallback: str) -> Transaction | None:
    """
    Validate and coerce a raw dict from Gemini into a Transaction TypedDict.
    Returns None if the dict is unparseable (silently drops bad rows).
    """
    try:
        date = str(raw.get("date", "")).strip()
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
            date = "1970-01-01"  # placeholder rather than dropping

        merchant = str(raw.get("merchant", "Unknown")).strip() or "Unknown"

        # amount — ensure positive float
        try:
            amount = abs(float(raw.get("amount", 0)))
        except (TypeError, ValueError):
            amount = 0.0

        txn_type = str(raw.get("transaction_type", "debit")).lower().strip()
        if txn_type not in VALID_TRANSACTION_TYPES:
            txn_type = "debit"

        category = str(raw.get("category", "others")).lower().strip()
        if category not in VALID_CATEGORIES:
            category = "others"

        # Infer month from date field; fall back to the PDF's month label
        month = date[:7] if len(date) >= 7 else month_fallback

        return Transaction(
            date=date,
            merchant=merchant,
            amount=amount,
            transaction_type=txn_type,
            category=category,
            month=month,
        )
    except Exception as exc:
        logger.warning("Skipping malformed transaction row: %s — %s", raw, exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Core LLM call (with retry)
# ─────────────────────────────────────────────────────────────────────────────


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_not_exception_type(GeminiNotConfiguredError),
    reraise=True,
)
def _call_gemini(pdf_text: str) -> str:
    """Call Gemini Flash and return the raw text response."""
    llm = _get_llm()
    truncated = pdf_text[:PDF_TEXT_CHAR_LIMIT]
    prompt = TRANSACTION_PARSE_PROMPT.format(pdf_text=truncated)
    response = llm.invoke(prompt)
    # .text joins the text blocks; newer models return content as a list of blocks
    return response.text


def _chunk_text(text: str, limit: int = PDF_TEXT_CHAR_LIMIT) -> list[str]:
    """
    Split statement text into parts of at most `limit` chars, breaking only
    between lines so no transaction row is cut in half. Long statements used
    to be truncated, which silently dropped their last transactions.
    """
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for line in text.splitlines():
        while len(line) > limit:  # a single huge line: hard split
            if current:
                chunks.append("\n".join(current))
                current, size = [], 0
            chunks.append(line[:limit])
            line = line[limit:]
        if size + len(line) + 1 > limit and current:
            chunks.append("\n".join(current))
            current, size = [], 0
        current.append(line)
        size += len(line) + 1
    if current:
        chunks.append("\n".join(current))
    return [c for c in chunks if c.strip()]


JSON_ATTEMPTS = 2  # a malformed or off-topic response gets one more try


def _parse_chunk(chunk: str, month_fallback: str) -> list[Transaction] | None:
    """
    Parse one part of a statement. A response that isn't a JSON list is
    retried once (the benchmark caught Gemini occasionally returning broken
    or unrelated output, which used to drop the whole statement). Returns []
    if Gemini still answers badly, and None if Gemini could not be reached.
    """
    raw_list = None
    for attempt in range(1, JSON_ATTEMPTS + 1):
        try:
            raw_response = _call_gemini(chunk)
        except GeminiNotConfiguredError:
            raise
        except Exception as exc:
            logger.error("Gemini call failed after retries: %s", exc)
            return None

        cleaned = _clean_gemini_json(raw_response)
        try:
            raw_list = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.warning(
                "Invalid JSON from Gemini (attempt %d/%d): %s — %.200s", attempt, JSON_ATTEMPTS, exc, cleaned
            )
            raw_list = None
            continue
        if isinstance(raw_list, list):
            break
        logger.warning("Gemini returned %s instead of a list (attempt %d)", type(raw_list).__name__, attempt)
        raw_list = None

    if raw_list is None:
        logger.error("No valid transaction list from Gemini after %d attempts", JSON_ATTEMPTS)
        return []

    transactions: list[Transaction] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        txn = _normalise_transaction(item, month_fallback)
        if txn is not None:
            transactions.append(txn)
    return transactions


_MONTH_NAME = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
    r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)
# The date formats Indian issuers print on transaction rows: 05/02/2026,
# 05-02-26, 05.02.2026, 2026-02-05, 05 Feb 26, 05-Feb-2026, Feb 05, 2026.
_DATE_RE = re.compile(
    r"(?<!\d)\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}(?!\d)"
    r"|(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)"
    rf"|(?<!\d)\d{{1,2}}[\s-]?{_MONTH_NAME}\b"
    rf"|\b{_MONTH_NAME}\s+\d{{1,2}},?\s+\d{{2,4}}(?!\d)",
    re.IGNORECASE,
)
_ROW_WINDOW = 2  # a wrapped row can print its date up to two lines above the amount


def _amount_re(amount: float) -> re.Pattern[str]:
    """Match an amount as printed once commas are removed: 9999, 9999.00, 2370.4, 2370.40."""
    whole, paise = divmod(round(amount * 100), 100)
    fraction = r"(?:\.0{1,2})?" if paise == 0 else rf"\.{paise // 10}{paise % 10 if paise % 10 else '0?'}"
    return re.compile(rf"(?<!\d)(?<!\d\.){whole}{fraction}(?![\d])")


def _drop_rows_without_a_dated_line(transactions: list[Transaction], text: str) -> list[Transaction]:
    """
    Keep only rows whose amount appears on a line with a date (or just below
    one, for wrapped rows). Statements often carry tables that aren't spending,
    like SBI's schedule of charges listing every card with its annual fee, and
    Gemini sometimes returns those as purchases with a made-up date. Their
    lines have amounts but no dates, so they are dropped here.

    Text with no dated lines at all is a layout we don't recognise, so nothing
    is dropped; nor is anything when every row would go.
    """
    lines = [line.replace(",", "") for line in text.splitlines()]
    dated = [bool(_DATE_RE.search(line)) for line in lines]
    if not transactions or not any(dated):
        return transactions

    def on_dated_line(txn: Transaction) -> bool:
        pattern = _amount_re(txn["amount"])
        return any(
            pattern.search(line) and any(dated[max(0, i - _ROW_WINDOW) : i + 1])
            for i, line in enumerate(lines)
        )

    kept = [t for t in transactions if on_dated_line(t)]
    if not kept:
        logger.warning("No parsed row matched a dated line; keeping all %d rows", len(transactions))
        return transactions
    if len(kept) < len(transactions):
        logger.info(
            "Dropped %d rows that aren't on a dated statement line (e.g. a fee table)",
            len(transactions) - len(kept),
        )
    return kept


def _parse_transactions_from_text(pdf_text: str, month_fallback: str) -> list[Transaction]:
    """
    Send pdf_text to Gemini (in parts when it is longer than
    PDF_TEXT_CHAR_LIMIT) and parse the JSON responses into Transaction dicts.
    A part that fails is skipped and the rest are kept. Raises
    GeminiNotConfiguredError when no API key is configured, and
    GeminiUnavailableError when no Gemini call succeeded at all (an invalid
    key, exhausted quota or outage), since the statement would otherwise
    parse to nothing and the user would get an empty, meaningless result.
    """
    if not pdf_text.strip():
        logger.warning("pdf_text is empty — skipping Gemini call")
        return []

    chunks = _chunk_text(pdf_text)
    transactions: list[Transaction] = []
    reached = False
    for chunk in chunks:
        parsed = _parse_chunk(chunk, month_fallback)
        if parsed is not None:
            reached = True
            transactions.extend(parsed)
    if not reached:
        raise GeminiUnavailableError("every Gemini call for this statement failed")
    transactions = _drop_rows_without_a_dated_line(transactions, pdf_text)

    logger.info(
        "Parsed %d transactions from statement (month=%s, parts=%d)",
        len(transactions),
        month_fallback,
        len(chunks),
    )
    return transactions


# ─────────────────────────────────────────────────────────────────────────────
# Multi-month text splitter
# ─────────────────────────────────────────────────────────────────────────────


def _split_by_month(pdf_text: str, months: list[str]) -> list[tuple[str, str]]:
    """
    Split concatenated multi-month text (produced by pdf_node) back into
    per-month chunks by the === STATEMENT: YYYY-MM === separators.

    Returns list of (month_label, text_chunk) tuples.
    Falls back to treating the entire text as one chunk with months[0].
    """
    separator_pattern = re.compile(r"=== STATEMENT: ([0-9]{4}-[0-9]{2}) ===")
    splits = separator_pattern.split(pdf_text)

    # splits = ["preamble", "2024-01", "text for jan", "2024-02", "text for feb", ...]
    if len(splits) < 3:
        # No separators found — treat as single month
        fallback = months[0] if months else "2024-01"
        return [(fallback, pdf_text)]

    chunks: list[tuple[str, str]] = []
    # splits[0] is text before first separator (usually empty)
    for i in range(1, len(splits), 2):
        month_label = splits[i]
        chunk_text = splits[i + 1] if i + 1 < len(splits) else ""
        chunks.append((month_label, chunk_text))

    return chunks


# ─────────────────────────────────────────────────────────────────────────────
# Node
# ─────────────────────────────────────────────────────────────────────────────


async def parse_transactions_node(state: AnalysisState) -> dict[str, Any]:
    """
    LangGraph node — parse transactions for the current card.
    Returns a dict of state fields to update.
    """
    cards: list[CardState] = deepcopy(state["cards"])
    card_idx: int = state["current_card_idx"]
    card: CardState = cards[card_idx]

    pdf_text: str = card.get("pdf_text", "")
    months: list[str] = card.get("months") or ["2024-01"]

    if not pdf_text.strip():
        logger.warning("parse_transactions_node: empty pdf_text for card_idx=%d", card_idx)
        card["transactions"] = []
        card["total_spend"] = 0.0
        card["status"] = "questioning"
        cards[card_idx] = card
        return {
            "cards": cards,
            "status": "questioning",
            "ui_action": "show_loading",
            "error": None,
        }

    # ── Parse per month chunk ─────────────────────────────────────────
    month_chunks = _split_by_month(pdf_text, months)
    all_transactions: list[Transaction] = []

    for month_label, chunk_text in month_chunks:
        logger.info(
            "Parsing month=%s for card_idx=%d (chunk_len=%d)",
            month_label,
            card_idx,
            len(chunk_text),
        )
        try:
            # Gemini's client is synchronous; run it off the event loop so one
            # slow statement doesn't stall every other request.
            txns = await asyncio.to_thread(_parse_transactions_from_text, chunk_text, month_label)
        except GeminiNotConfiguredError:
            logger.error("GEMINI_API_KEY is not set: cannot parse statements")
            card["status"] = "error"
            cards[card_idx] = card
            return {
                "cards": cards,
                "status": "error",
                "ui_action": "show_error",
                "error": "Statement analysis is not available right now: the AI service is not configured.",
            }
        except GeminiUnavailableError:
            logger.error("Gemini failed for every part of card_idx=%d month=%s", card_idx, month_label)
            card["status"] = "error"
            cards[card_idx] = card
            return {
                "cards": cards,
                "status": "error",
                "ui_action": "show_error",
                "error": "We couldn't read the transactions in your statement because the AI service "
                "didn't respond. Please try again in a minute.",
            }
        # Ensure every transaction carries the correct month label
        for txn in txns:
            if not txn.get("month") or txn["month"] == "1970-01":
                txn["month"] = month_label
        all_transactions.extend(txns)

    # ── Compute total spend (debits only) ─────────────────────────────
    total_spend = sum(t["amount"] for t in all_transactions if t.get("transaction_type") == "debit")

    card["transactions"] = all_transactions
    card["total_spend"] = round(total_spend, 2)
    card["status"] = "questioning"
    cards[card_idx] = card

    logger.info(
        "parse_transactions_node complete — card_idx=%d txns=%d total_spend=%.2f",
        card_idx,
        len(all_transactions),
        total_spend,
    )

    return {
        "cards": cards,
        "status": "questioning",
        "ui_action": "show_loading",
        "error": None,
    }
