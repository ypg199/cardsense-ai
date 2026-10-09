"""
agents/pdf_node.py
─────────────────────────────────────────────────────────────────────────────
Node 1: pdf_check_node

Responsibilities
────────────────
1. Receive raw PDF bytes for the current card.
2. Check for encryption.  If locked and no password supplied → interrupt.
3. Authenticate with supplied password; surface wrong-password errors.
4. Extract text via pdfplumber (tables-aware) with PyMuPDF as fallback.
5. Write extracted text + status back to AnalysisState.

State fields read
─────────────────
  cards[current_card_idx].pdf_bytes_list   – list[bytes], one per month
  cards[current_card_idx].pdf_passwords    – list[str|None], parallel to above
  current_card_idx

State fields written
────────────────────
  cards[current_card_idx].pdf_text         – concatenated text from all PDFs
  cards[current_card_idx].pdf_encrypted    – bool
  cards[current_card_idx].pdf_bytes_list   – cleared to [] after extraction
  cards[current_card_idx].status           – "parsing" | "pdf_locked"
  status                                   – mirrors card status
  ui_action                                – "show_password_input" | "show_loading"
  locked_card_idx                          – set when PDF is locked
  locked_pdf_idx                           – index of locked PDF within card
  error                                    – set on unrecoverable failure
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import io
import logging
from copy import deepcopy
from typing import Any

import fitz          # PyMuPDF
import pdfplumber

from agents.state import AnalysisState, CardState

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _extract_with_pdfplumber(pdf_bytes: bytes) -> str:
    """
    Primary extractor — pdfplumber.
    Uses extract_tables() first (better for columnar statements),
    then extract_text() as fallback per page.
    Raises on failure so caller can switch to PyMuPDF.
    """
    pages_text: list[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            parts: list[str] = []

            # Tables first — join cells with tab, rows with newline
            tables = page.extract_tables() or []
            for table in tables:
                for row in table:
                    if row:
                        parts.append("\t".join(cell or "" for cell in row))

            # Plain text fallback for non-table content
            plain = page.extract_text() or ""
            if plain.strip():
                parts.append(plain)

            pages_text.append("\n".join(parts))

    return "\n\n".join(pages_text)


def _extract_with_pymupdf(pdf_bytes: bytes) -> str:
    """
    Fallback extractor — PyMuPDF.
    Used when pdfplumber raises or returns empty text.
    """
    pages_text: list[str] = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    for page in doc:
        pages_text.append(page.get_text("text"))
    doc.close()
    return "\n\n".join(pages_text)


def _extract_text(pdf_bytes: bytes, month_label: str) -> str:
    """
    Try pdfplumber → fall back to PyMuPDF → fall back to empty string.
    Never raises.
    """
    # pdfplumber attempt
    try:
        text = _extract_with_pdfplumber(pdf_bytes)
        if text.strip():
            logger.debug("pdfplumber succeeded for month=%s (%d chars)", month_label, len(text))
            return text
        logger.warning("pdfplumber returned empty text for month=%s, trying PyMuPDF", month_label)
    except Exception as exc:
        logger.warning("pdfplumber failed for month=%s: %s — trying PyMuPDF", month_label, exc)

    # PyMuPDF attempt
    try:
        text = _extract_with_pymupdf(pdf_bytes)
        if text.strip():
            logger.debug("PyMuPDF succeeded for month=%s (%d chars)", month_label, len(text))
            return text
        logger.warning("PyMuPDF also returned empty text for month=%s", month_label)
    except Exception as exc:
        logger.error("PyMuPDF failed for month=%s: %s", month_label, exc)

    return ""


def _decrypt_pdf(pdf_bytes: bytes, password: str | None) -> tuple[bytes, bool]:
    """
    Open a PDF, authenticate if needed, return (decrypted_bytes, was_encrypted).

    Returns
    -------
    (bytes, bool)  — decrypted PDF bytes and whether it was encrypted.

    Raises
    ------
    ValueError("pdf_locked")       — encrypted, no password provided
    ValueError("wrong_password")   — password rejected by fitz
    RuntimeError                   — corrupt / unreadable PDF
    """
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise RuntimeError(f"Cannot open PDF: {exc}") from exc

    was_encrypted = doc.is_encrypted

    if not was_encrypted:
        # Not encrypted — return bytes as-is
        doc.close()
        return pdf_bytes, False

    # Encrypted — try opening without password first (some PDFs self-authenticate)
    if doc.authenticate("") > 0:
        logger.info("PDF self-authenticated (empty password)")
        buf = io.BytesIO()
        doc.save(buf)
        doc.close()
        return buf.getvalue(), True

    # Need a real password
    if not password:
        doc.close()
        raise ValueError("pdf_locked")

    result = doc.authenticate(password)
    if result == 0:
        doc.close()
        raise ValueError("wrong_password")

    # Authenticated — export decrypted bytes
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue(), True


# ─────────────────────────────────────────────────────────────────────────────
# Node
# ─────────────────────────────────────────────────────────────────────────────

def pdf_check_node(state: AnalysisState) -> dict[str, Any]:
    """
    LangGraph node.  Processes all PDFs for the current card.

    Returns a dict of state fields to update (LangGraph merge semantics).
    """
    cards: list[CardState] = deepcopy(state["cards"])
    card_idx: int = state["current_card_idx"]
    card: CardState = cards[card_idx]

    pdf_bytes_list: list[bytes] = card.get("pdf_bytes_list") or []
    pdf_passwords: list[str | None] = card.get("pdf_passwords") or []
    months: list[str] = card.get("months") or []

    if not pdf_bytes_list:
        logger.error("pdf_check_node: no PDF bytes for card_idx=%d", card_idx)
        card["status"] = "error"
        cards[card_idx] = card
        return {
            "cards": cards,
            "status": "error",
            "ui_action": "show_error",
            "error": f"No PDF uploaded for card '{card.get('card_name', card_idx)}'",
        }

    all_text_parts: list[str] = []
    any_encrypted = False

    for pdf_idx, pdf_bytes in enumerate(pdf_bytes_list):
        password = pdf_passwords[pdf_idx] if pdf_idx < len(pdf_passwords) else None
        month_label = months[pdf_idx] if pdf_idx < len(months) else f"month_{pdf_idx + 1}"

        # ── Decrypt / check encryption ────────────────────────────────
        try:
            decrypted_bytes, was_encrypted = _decrypt_pdf(pdf_bytes, password)
            if was_encrypted:
                any_encrypted = True

        except ValueError as exc:
            reason = str(exc)

            if reason == "pdf_locked":
                logger.info(
                    "PDF locked — card_idx=%d pdf_idx=%d month=%s",
                    card_idx, pdf_idx, month_label,
                )
                card["pdf_encrypted"] = True
                card["status"] = "pdf_locked"
                cards[card_idx] = card
                return {
                    "cards": cards,
                    "status": "pdf_locked",
                    "ui_action": "show_password_input",
                    "locked_card_idx": card_idx,
                    "locked_pdf_idx": pdf_idx,
                    "error": None,
                }

            if reason == "wrong_password":
                logger.warning(
                    "Wrong password — card_idx=%d pdf_idx=%d month=%s",
                    card_idx, pdf_idx, month_label,
                )
                card["pdf_encrypted"] = True
                card["status"] = "pdf_locked"
                cards[card_idx] = card
                return {
                    "cards": cards,
                    "status": "pdf_locked",
                    "ui_action": "show_password_input",
                    "locked_card_idx": card_idx,
                    "locked_pdf_idx": pdf_idx,
                    "error": "Wrong password — please try again.",
                }

            # Unexpected ValueError
            raise

        except RuntimeError as exc:
            logger.error("Corrupt PDF — card_idx=%d pdf_idx=%d: %s", card_idx, pdf_idx, exc)
            card["status"] = "error"
            cards[card_idx] = card
            return {
                "cards": cards,
                "status": "error",
                "ui_action": "show_error",
                "error": f"Could not read PDF for {month_label}: {exc}",
            }

        # ── Extract text ──────────────────────────────────────────────
        text = _extract_text(decrypted_bytes, month_label)
        if text.strip():
            # Prefix each month's text with a clear separator for the parser
            all_text_parts.append(f"=== STATEMENT: {month_label} ===\n{text}")
        else:
            logger.warning("Empty text extracted for card_idx=%d month=%s", card_idx, month_label)

    # ── Commit results ────────────────────────────────────────────────
    full_text = "\n\n".join(all_text_parts)

    card["pdf_text"] = full_text
    card["pdf_encrypted"] = any_encrypted
    card["status"] = "parsing"
    # Clear raw bytes — don't bloat LangGraph checkpoints
    card["pdf_bytes_list"] = []

    cards[card_idx] = card

    logger.info(
        "pdf_check_node complete — card_idx=%d cards=%d text_len=%d encrypted=%s",
        card_idx, len(cards), len(full_text), any_encrypted,
    )

    return {
        "cards": cards,
        "status": "parsing",
        "ui_action": "show_loading",
        "locked_card_idx": None,
        "locked_pdf_idx": None,
        "error": None,
    }
