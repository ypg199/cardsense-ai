"""
agents/state.py
─────────────────────────────────────────────────────────────────────────────
AnalysisState TypedDict — the single shared state object passed between
every LangGraph node in the CardSense AI pipeline.

All fields listed here correspond 1-to-1 with the MongoDB sessions document
(db/schemas.py) plus in-flight fields that exist only within the graph
execution and are never persisted directly.
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from typing import TypedDict

# ─────────────────────────────────────────────────────────────────────────────
# Sub-type helpers (plain dicts — kept simple for LangGraph serialisation)
# ─────────────────────────────────────────────────────────────────────────────


class Transaction(TypedDict):
    """A single parsed debit/credit line from a bank statement."""

    date: str  # "YYYY-MM-DD"
    merchant: str  # Cleaned merchant name
    amount: float  # Positive INR amount
    transaction_type: str  # "debit" | "credit" | "refund"
    category: str  # One of the 16 standard categories
    month: str  # Source month label e.g. "2024-01"


class MonthlyBreakdown(TypedDict):
    """Per-month cashback summary produced by cashback_calc_node."""

    month: str
    earned: float
    missed: float
    score: int


class CashbackResult(TypedDict):
    """Output of cashback_calc_node for a single card."""

    earned_breakdown: dict[str, float]  # { category: INR earned }
    missed_breakdown: dict[str, float]  # { category: INR missed }
    utilization_score: int  # 0-100
    monthly_breakdown: list[MonthlyBreakdown]
    trend: str  # "improving" | "declining" | "flat" | "single_month"


class CardRecommendation(TypedDict):
    """A single alternative card recommendation from compare_node."""

    card_id: str
    card_name: str
    bank: str
    estimated_monthly_cashback: float
    estimated_annual_cashback: float
    improvement_over_current_monthly: float
    why_better: str  # 2 sentences with specific % and ₹ amounts
    best_categories: list[str]
    caveat: str | None


class ComparisonResult(TypedDict):
    """Output of compare_node."""

    verdict: str  # "Good fit" | "Could do better" | "Switch recommended"
    verdict_reason: str  # One sentence with numbers
    card_score: int  # 0-100 overall efficiency score
    recommendations: list[CardRecommendation]
    routing_advice: list[str]  # Multi-card: "Use Axis Airtel for Zomato (25% vs 1%)"
    tips: list[str]  # 3-5 actionable tips


class Question(TypedDict):
    """A single YES/NO utilization question shown to the user."""

    id: str
    category: str  # Benefit category key, or "general"
    text: str  # Full question text
    hint: str  # e.g. "Earns 25% cashback — ₹300 potential this month"
    detected_spend: float  # Sum of txn amounts in this category
    potential_cashback: float  # detected_spend × benefit rate
    is_general: bool  # True for generic usage questions


class CardState(TypedDict):
    """Per-card slice of state. One entry per uploaded card."""

    card_id: str
    card_name: str  # Denormalised from DB for convenience
    months: list[str]  # e.g. ["2024-01", "2024-02"]

    # ── PDF pipeline ─────────────────────────────────────────────────────
    pdf_bytes_list: list[bytes]  # Raw bytes for each uploaded PDF (in-flight only)
    pdf_passwords: list[str | None]  # Per-PDF password attempts (parallel to pdf_bytes_list)
    pdf_encrypted: bool  # True if any PDF in this card is/was encrypted
    pdf_text: str  # Concatenated extracted text from all PDFs

    # ── Parsing ──────────────────────────────────────────────────────────
    transactions: list[Transaction]
    total_spend: float  # Sum of all debit transaction amounts

    # ── Quiz ─────────────────────────────────────────────────────────────
    pending_questions: list[Question]  # Questions not yet answered by user
    answered_questions: list[Question]  # Questions already answered (auto or manual)
    qa_answers: dict[str, bool]  # { question_id: True/False }

    # ── Results ──────────────────────────────────────────────────────────
    cashback_result: CashbackResult | None
    utilization_score: int  # 0-100 mirror of cashback_result.utilization_score

    # ── Per-card status ───────────────────────────────────────────────────
    status: str  # Mirrors top-level status but scoped to this card


# ─────────────────────────────────────────────────────────────────────────────
# AnalysisState — the top-level LangGraph state TypedDict
# ─────────────────────────────────────────────────────────────────────────────


class AnalysisState(TypedDict):
    """
    Shared state passed between every node in the LangGraph pipeline.

    ── Lifecycle ────────────────────────────────────────────────────────────
    1. Created by POST /session/start with session_id, cards[], status="uploading"
    2. pdf_check_node fills pdf_text (or sets status="pdf_locked")
    3. parse_transactions_node fills transactions[]
    4. question_gen_node fills pending_questions[]
    5. Graph interrupts at wait_answer; user submits answers via HTTP
    6. cashback_calc_node fills cashback_result + utilization_score
    7. compare_node fills comparison_result; status="done"

    ── Persistence ──────────────────────────────────────────────────────────
    LangGraph checkpoints this dict into MongoDB via AsyncMongoDBSaver.
    thread_id = session_id.  All bytes fields (pdf_bytes_list) are transient
    and cleared after pdf extraction to avoid bloating the checkpoint.
    """

    # ── Session identity ──────────────────────────────────────────────────
    session_id: str  # UUID v4; also used as LangGraph thread_id

    # ── Top-level pipeline status ─────────────────────────────────────────
    # "uploading" | "pdf_locked" | "parsing" | "questioning" |
    # "calculating" | "comparing" | "done" | "error"
    status: str

    # ── Multi-card data ───────────────────────────────────────────────────
    cards: list[CardState]  # One entry per selected card
    current_card_idx: int  # Which card is currently being processed

    # ── Password flow ─────────────────────────────────────────────────────
    # When status == "pdf_locked":
    #   - locked_card_idx  → which card's PDF needs a password
    #   - locked_pdf_idx   → which PDF within that card (0-based)
    locked_card_idx: int | None
    locked_pdf_idx: int | None

    # ── Active question (graph interrupted at wait_answer) ─────────────────
    # The single question currently presented to the user via the API.
    # Null when not in questioning state.
    current_question: Question | None

    # ── Cross-card comparison (populated by compare_node) ─────────────────
    comparison_result: ComparisonResult | None

    # ── ui_action hint for the frontend ───────────────────────────────────
    # Tells the React frontend which component to render next.
    # "show_upload" | "show_password_input" | "show_loading" |
    # "show_question" | "show_utilization" | "show_results" | "show_analyser" |
    # "show_error"
    ui_action: str

    # ── Aggregate helpers (computed, not stored in MongoDB) ────────────────
    total_questions_count: int  # Total questions across all cards
    answered_questions_count: int  # How many have been answered so far

    # ── Error handling ────────────────────────────────────────────────────
    error: str | None  # Error message if status == "error"

    # ── Metadata ─────────────────────────────────────────────────────────
    created_at: str  # ISO-8601 timestamp

    # "full" runs the whole pipeline; "spend" stops after parsing, for the
    # standalone Spend Analyser (no quiz, cashback score or comparison).
    mode: str
    sample: bool  # True for the built-in sample statements (fictitious data)
