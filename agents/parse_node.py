"""
agents/parse_node.py
─────────────────────────────────────────────────────────────────────────────
Node 2: parse_transactions_node

Responsibilities
────────────────
1. Take the extracted pdf_text for the current card.
2. Send (up to 10 000 chars) to gemini-2.5-flash with the exact prompt
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

from agents.state import AnalysisState, CardState, Transaction

load_dotenv()
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

PDF_TEXT_CHAR_LIMIT = 10_000  # Truncate before sending to Gemini (spec: 10 000 chars)

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

Statement text (truncated to 10000 chars):
{pdf_text}"""


# ─────────────────────────────────────────────────────────────────────────────
# Gemini client (lazy-initialised so tests can mock before import)
# ─────────────────────────────────────────────────────────────────────────────


class GeminiNotConfiguredError(RuntimeError):
    """Raised when GEMINI_API_KEY is missing, so parsing can't run at all."""


def _get_llm():
    """Return a ChatGoogleGenerativeAI instance for gemini-2.5-flash."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise GeminiNotConfiguredError("GEMINI_API_KEY is not set")
    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=api_key,
        temperature=0,
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
    return response.content


def _parse_transactions_from_text(pdf_text: str, month_fallback: str) -> list[Transaction]:
    """
    Send pdf_text to Gemini and parse the JSON response into Transaction dicts.
    Returns an empty list on failure. Raises GeminiNotConfiguredError only
    when no API key is configured, since every statement would then parse
    to nothing and the user would get a meaningless score.
    """
    if not pdf_text.strip():
        logger.warning("pdf_text is empty — skipping Gemini call")
        return []

    try:
        raw_response = _call_gemini(pdf_text)
    except GeminiNotConfiguredError:
        raise
    except Exception as exc:
        logger.error("Gemini call failed after retries: %s", exc)
        return []

    cleaned = _clean_gemini_json(raw_response)

    try:
        raw_list = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.error("JSON parse error after cleaning: %s\nCleaned text: %.500s", exc, cleaned)
        return []

    if not isinstance(raw_list, list):
        logger.error("Gemini returned non-list JSON: %s", type(raw_list))
        return []

    transactions: list[Transaction] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        txn = _normalise_transaction(item, month_fallback)
        if txn is not None:
            transactions.append(txn)

    logger.info("Parsed %d transactions from statement (month=%s)", len(transactions), month_fallback)
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
