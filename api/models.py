"""
api/models.py
─────────────────────────────────────────────────────────────────────────────
Pydantic request/response models for all FastAPI endpoints.
Every session endpoint returns a SessionResponse.
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# ─────────────────────────────────────────────────────────────────────────────
# Sub-models
# ─────────────────────────────────────────────────────────────────────────────


class QuestionOut(BaseModel):
    id: str
    category: str
    text: str
    hint: str
    detected_spend: float
    potential_cashback: float
    is_general: bool


class CardSummaryOut(BaseModel):
    card_id: str
    card_name: str
    months: list[str]
    transactions_count: int
    total_spend: float
    pdf_encrypted: bool
    status: str
    cashback_result: CashbackResultOut | None = None


class MonthlyBreakdownOut(BaseModel):
    month: str
    earned: float
    missed: float
    score: int


class CashbackResultOut(BaseModel):
    earned_breakdown: dict[str, float]
    missed_breakdown: dict[str, float]
    utilization_score: int
    monthly_breakdown: list[MonthlyBreakdownOut]
    trend: str


class CardRecommendationOut(BaseModel):
    card_id: str
    card_name: str
    bank: str
    estimated_monthly_cashback: float
    estimated_annual_cashback: float
    improvement_over_current_monthly: float
    why_better: str
    best_categories: list[str]
    caveat: str | None


class ComparisonResultOut(BaseModel):
    verdict: str
    verdict_reason: str
    card_score: int
    recommendations: list[CardRecommendationOut]
    routing_advice: list[str]
    tips: list[str]


# ─────────────────────────────────────────────────────────────────────────────
# SessionResponse — returned by every session endpoint (Section 6)
# ─────────────────────────────────────────────────────────────────────────────


class SessionResponse(BaseModel):
    session_id: str
    status: str
    ui_action: str
    mode: str = "full"  # "spend" for a standalone Spend Analyser session
    current_card_idx: int

    cards: list[CardSummaryOut]

    # Present during quiz
    current_question: QuestionOut | None = None
    questions_answered: int = 0
    questions_total: int = 0

    # Present after cashback calculation
    cashback_result: CashbackResultOut | None = None

    # Present after compare
    comparison_result: ComparisonResultOut | None = None

    error: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Spend analyser
# ─────────────────────────────────────────────────────────────────────────────


class SpendCardOut(BaseModel):
    card_id: str
    card_name: str


class SpendMonthOut(BaseModel):
    month: str
    total: float
    count: int
    by_category: dict[str, float] = {}
    by_card: dict[str, float] = {}


class SpendCategoryOut(BaseModel):
    category: str
    total: float
    share: float
    count: int


class SpendMerchantOut(BaseModel):
    merchant: str
    total: float
    count: int
    category: str


class SpendTransactionOut(BaseModel):
    date: str
    merchant: str
    amount: float
    category: str
    card_name: str


class SpendSummaryResponse(BaseModel):
    session_id: str
    card_id: str | None = None
    cards: list[SpendCardOut]
    months: list[str]
    total_spend: float
    refunds: float
    transactions: int
    monthly: list[SpendMonthOut]
    categories: list[SpendCategoryOut]
    merchants: list[SpendMerchantOut]
    largest: list[SpendTransactionOut]


# ─────────────────────────────────────────────────────────────────────────────
# Request bodies
# ─────────────────────────────────────────────────────────────────────────────


class PasswordRequest(BaseModel):
    password: str = Field(..., min_length=1, max_length=128)
    card_idx: int = Field(0, ge=0)


class AnswerRequest(BaseModel):
    question_id: str = Field(..., min_length=1, max_length=128)
    answer: bool
    card_idx: int = Field(0, ge=0)


class CrawlRequest(BaseModel):
    sources: list[str] | None = None
    direct_urls: list[str] | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Card list / search responses
# ─────────────────────────────────────────────────────────────────────────────


class BenefitOut(BaseModel):
    category: str = "others"
    label: str = ""
    rate: float = 0.0  # crawler may store None — default to 0
    max_cashback_per_month: float | None = None
    reward_type: str = "cashback"
    point_value_inr: float | None = None
    conditions: str | None = None
    merchant_keywords: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class CardDetailOut(BaseModel):
    id: str = Field(alias="_id")
    name: str
    bank: str
    network: str | None = None  # crawler may not always extract this
    card_type: str = "cashback"
    annual_fee: int = 0
    fee_waiver_spend: int | None = None
    joining_fee: int = 0
    min_annual_income: int | None = None
    min_credit_score: int | None = None
    benefits: list[BenefitOut] = Field(default_factory=list)
    best_for_tags: list[str] = Field(default_factory=list)
    not_good_for: list[str] = Field(default_factory=list)
    source_url: str | None = None
    last_crawled: str | None = None

    model_config = {"populate_by_name": True}


class CardListResponse(BaseModel):
    count: int
    cards: list[CardDetailOut]


class CrawlJobResponse(BaseModel):
    job_id: str
    message: str


class CrawlJobStatusOut(BaseModel):
    job_id: str
    status: str
    cards_upserted: int = 0
    cards_failed: int = 0
    created_at: str | None = None
    finished_at: str | None = None


class CrawlJobListResponse(BaseModel):
    jobs: list[CrawlJobStatusOut]
