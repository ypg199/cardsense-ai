"""
api/routes/session.py
─────────────────────────────────────────────────────────────────────────────
Session endpoints — the core interactive flow of CardSense AI.

POST /session/start          — upload PDFs, kick off pipeline
POST /session/{id}/password  — supply password for encrypted PDF
POST /session/{id}/answer    — submit one YES/NO quiz answer
GET  /session/{id}/status    — poll current graph state
POST /session/{id}/add_card  — add a new card to an existing session
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import logging
import uuid
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from api.models import (
    AnswerRequest,
    CardSummaryOut,
    CashbackResultOut,
    ComparisonResultOut,
    MonthlyBreakdownOut,
    CardRecommendationOut,
    PasswordRequest,
    QuestionOut,
    SessionResponse,
)
from agents.state import AnalysisState, CardState
from api.settings import MAX_FILES_PER_REQUEST, MAX_UPLOAD_BYTES, MAX_UPLOAD_MB, SESSION_TTL_HOURS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/session", tags=["session"])


# ─────────────────────────────────────────────────────────────────────────────
# State → SessionResponse converter
# ─────────────────────────────────────────────────────────────────────────────

def _state_to_response(state: AnalysisState) -> SessionResponse:
    """Convert a LangGraph AnalysisState dict into a SessionResponse."""

    cards_out: list[CardSummaryOut] = []
    for card in state.get("cards", []):
        cards_out.append(CardSummaryOut(
            card_id=card.get("card_id", ""),
            card_name=card.get("card_name", ""),
            months=card.get("months", []),
            transactions_count=len(card.get("transactions", [])),
            total_spend=card.get("total_spend", 0.0),
            pdf_encrypted=card.get("pdf_encrypted", False),
            status=card.get("status", "uploading"),
        ))

    # current_question
    cq_raw = state.get("current_question")
    cq_out: QuestionOut | None = None
    if cq_raw:
        cq_out = QuestionOut(
            id=cq_raw.get("id", ""),
            category=cq_raw.get("category", ""),
            text=cq_raw.get("text", ""),
            hint=cq_raw.get("hint", ""),
            detected_spend=cq_raw.get("detected_spend", 0.0),
            potential_cashback=cq_raw.get("potential_cashback", 0.0),
            is_general=cq_raw.get("is_general", False),
        )

    # cashback_result — from active card
    cr_out: CashbackResultOut | None = None
    card_idx = state.get("current_card_idx", 0)
    cards_list = state.get("cards", [])
    if cards_list and card_idx < len(cards_list):
        cr_raw = cards_list[card_idx].get("cashback_result")
        if cr_raw:
            cr_out = CashbackResultOut(
                earned_breakdown=cr_raw.get("earned_breakdown", {}),
                missed_breakdown=cr_raw.get("missed_breakdown", {}),
                utilization_score=cr_raw.get("utilization_score", 0),
                monthly_breakdown=[
                    MonthlyBreakdownOut(**mb)
                    for mb in cr_raw.get("monthly_breakdown", [])
                ],
                trend=cr_raw.get("trend", "single_month"),
            )

    # comparison_result
    comp_out: ComparisonResultOut | None = None
    comp_raw = state.get("comparison_result")
    if comp_raw:
        recs = [
            CardRecommendationOut(
                card_id=r.get("card_id", ""),
                card_name=r.get("card_name", ""),
                bank=r.get("bank", ""),
                estimated_monthly_cashback=r.get("estimated_monthly_cashback", 0),
                estimated_annual_cashback=r.get("estimated_annual_cashback", 0),
                improvement_over_current_monthly=r.get("improvement_over_current_monthly", 0),
                why_better=r.get("why_better", ""),
                best_categories=r.get("best_categories", []),
                caveat=r.get("caveat"),
            )
            for r in comp_raw.get("recommendations", [])
        ]
        comp_out = ComparisonResultOut(
            verdict=comp_raw.get("verdict", ""),
            verdict_reason=comp_raw.get("verdict_reason", ""),
            card_score=comp_raw.get("card_score", 0),
            recommendations=recs,
            routing_advice=comp_raw.get("routing_advice", []),
            tips=comp_raw.get("tips", []),
        )

    return SessionResponse(
        session_id=state.get("session_id", ""),
        status=state.get("status", "uploading"),
        ui_action=state.get("ui_action", "show_upload"),
        current_card_idx=state.get("current_card_idx", 0),
        cards=cards_out,
        current_question=cq_out,
        questions_answered=state.get("answered_questions_count", 0),
        questions_total=state.get("total_questions_count", 0),
        cashback_result=cr_out,
        comparison_result=comp_out,
        error=state.get("error"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# DB session persistence helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _save_session(state: AnalysisState) -> None:
    """Persist session state to MongoDB sessions collection."""
    try:
        from db.connection import get_db
        db = get_db()
        # Strip non-serialisable bytes before saving
        doc = deepcopy(state)
        for card in doc.get("cards", []):
            # Passwords are only needed for the request that supplies them.
            card["pdf_passwords"] = [None] * len(card.get("pdf_passwords") or [])
            # PDF bytes are only kept while the card waits for a password,
            # so the next request can decrypt them. Otherwise drop them.
            if card.get("status") != "pdf_locked":
                card["pdf_bytes_list"] = []
        doc["_id"] = doc["session_id"]
        doc["expires_at"] = datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)
        await db["sessions"].replace_one({"_id": doc["_id"]}, doc, upsert=True)
    except Exception as exc:
        logger.warning("Failed to persist session '%s': %s", state.get("session_id"), exc)


async def _load_session(session_id: str) -> AnalysisState | None:
    """Load session state from MongoDB."""
    try:
        from db.connection import get_db
        db = get_db()
        doc = await db["sessions"].find_one({"_id": session_id})
        if doc:
            doc["session_id"] = doc.pop("_id", session_id)
            doc.pop("expires_at", None)
            for card in doc.get("cards", []):
                card["pdf_bytes_list"] = [bytes(b) for b in card.get("pdf_bytes_list") or []]
            return doc
        return None
    except Exception as exc:
        logger.warning("Failed to load session '%s': %s", session_id, exc)
        return None


def _raise_not_found(session_id: str):
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Session '{session_id}' not found.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Upload validation
# ─────────────────────────────────────────────────────────────────────────────

async def _read_pdf_uploads(pdf_files: list[UploadFile]) -> list[bytes]:
    """Read uploaded PDFs, enforcing count, size and file-type limits."""
    if len(pdf_files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(
            status_code=422,
            detail=f"Too many files: at most {MAX_FILES_PER_REQUEST} PDFs per request.",
        )

    contents: list[bytes] = []
    for upload in pdf_files:
        data = await upload.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"'{upload.filename}' is larger than {MAX_UPLOAD_MB} MB.",
            )
        if not data.lstrip()[:5] == b"%PDF-":
            raise HTTPException(
                status_code=422,
                detail=f"'{upload.filename}' is not a PDF file.",
            )
        contents.append(data)
    return contents


# ─────────────────────────────────────────────────────────────────────────────
# Graph runner
# ─────────────────────────────────────────────────────────────────────────────

async def _run_graph(state: AnalysisState) -> AnalysisState:
    """
    Drive the pipeline by calling node functions directly as async functions.

    Routing is determined entirely by state["status"] — the status saved
    in MongoDB between HTTP calls tells us exactly where to resume.

    Pipeline stages:
      uploading / pdf_locked → pdf_check → parse → question_gen → [interrupt]
      questioning             →                     question_gen → [interrupt or continue]
      calculating             →                                    cashback_calc → compare
      comparing               →                                                   compare
    """
    from agents.pdf_node import pdf_check_node
    from agents.parse_node import parse_transactions_node
    from agents.question_node import question_gen_node
    from agents.cashback_node import cashback_calc_node
    from agents.compare_node import compare_node

    def _merge(base: dict, patch: dict) -> dict:
        return {**base, **patch}

    try:
        current = dict(state)
        entry_status = current.get("status", "uploading")

        logger.info(
            "_run_graph entry — session=%s status=%s",
            current.get("session_id", "?"), entry_status
        )

        # ── Fresh session: run full pipeline from PDF check ────────────────
        if entry_status in ("uploading", "pdf_locked"):
            patch = pdf_check_node(current)
            current = _merge(current, patch)
            if current["status"] == "error":
                await _save_session(current); return current
            if current["status"] == "pdf_locked":
                await _save_session(current); return current

            patch = await parse_transactions_node(current)
            current = _merge(current, patch)

            patch = await question_gen_node(current)
            current = _merge(current, patch)

            if current["ui_action"] == "show_question":
                await _save_session(current); return current

            # No questions — fall through to cashback
            patch = await cashback_calc_node(current)
            current = _merge(current, patch)
            patch = await compare_node(current)
            current = _merge(current, patch)

        # ── Resume from quiz: answer was just submitted ────────────────────
        elif entry_status == "questioning":
            patch = await question_gen_node(current)
            current = _merge(current, patch)

            if current["ui_action"] == "show_question":
                await _save_session(current); return current

            # All questions answered — continue to cashback + compare
            patch = await cashback_calc_node(current)
            current = _merge(current, patch)
            patch = await compare_node(current)
            current = _merge(current, patch)

        # ── Already at cashback/compare stage ─────────────────────────────
        elif entry_status == "calculating":
            patch = await cashback_calc_node(current)
            current = _merge(current, patch)
            patch = await compare_node(current)
            current = _merge(current, patch)

        elif entry_status == "comparing":
            patch = await compare_node(current)
            current = _merge(current, patch)

        elif entry_status in ("done", "error"):
            # Already finished — just return as-is
            pass

        else:
            logger.warning("_run_graph: unknown status '%s' — treating as done", entry_status)

    except Exception as exc:
        logger.exception("Pipeline error (session=%s)", state.get("session_id"))
        current = {
            **state,
            "status": "error",
            "error": "Something went wrong while analysing your statement. Please try again.",
            "ui_action": "show_error",
        }

    await _save_session(current)
    return current


# ─────────────────────────────────────────────────────────────────────────────
# POST /session/start
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/start", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def start_session(
    card_ids: Annotated[list[str], Form()],
    pdf_files: Annotated[list[UploadFile], File()],
    month_labels: Annotated[list[str], Form()],
):
    """
    Start a new analysis session.

    Body (multipart/form-data):
      card_ids[]    — one or more card slug strings
      pdf_files[]   — one PDF per card (or multiple per card for multi-month)
      month_labels[] — e.g. "2024-01" parallel to pdf_files[]

    The number of card_ids, pdf_files, and month_labels must match.
    Returns the full SessionResponse with ui_action reflecting the
    first graph pause point.
    """
    if not card_ids:
        raise HTTPException(status_code=422, detail="At least one card_id is required.")
    if not pdf_files:
        raise HTTPException(status_code=422, detail="At least one PDF file is required.")
    if len(pdf_files) != len(month_labels):
        raise HTTPException(
            status_code=422,
            detail=f"pdf_files ({len(pdf_files)}) and month_labels ({len(month_labels)}) must have equal length.",
        )

    # Read all PDF bytes eagerly (UploadFile objects close after request)
    pdf_bytes_map: dict[str, list[tuple[bytes, str]]] = {cid: [] for cid in card_ids}

    # Distribute PDFs to cards. Simple strategy: one PDF per card (in order).
    # If more PDFs than cards, assign excess to the last card.
    pdf_contents = await _read_pdf_uploads(pdf_files)
    for i, (pdf_data, month) in enumerate(zip(pdf_contents, month_labels)):
        card_idx = min(i, len(card_ids) - 1)
        card_id = card_ids[card_idx]
        pdf_bytes_map[card_id].append((pdf_data, month))

    # Look up card names from DB (best-effort)
    card_names: dict[str, str] = {}
    try:
        from db.connection import get_db
        db = get_db()
        for cid in card_ids:
            doc = await db["credit_cards"].find_one({"_id": cid}, {"name": 1})
            card_names[cid] = doc["name"] if doc else cid
    except Exception:
        card_names = {cid: cid for cid in card_ids}

    # Build initial state
    session_id = str(uuid.uuid4())
    cards: list[CardState] = []
    for cid in card_ids:
        pairs = pdf_bytes_map.get(cid, [])
        cards.append(CardState(
            card_id=cid,
            card_name=card_names.get(cid, cid),
            months=[m for _, m in pairs],
            pdf_bytes_list=[b for b, _ in pairs],
            pdf_passwords=[None] * len(pairs),
            pdf_encrypted=False,
            pdf_text="",
            transactions=[],
            total_spend=0.0,
            pending_questions=[],
            answered_questions=[],
            qa_answers={},
            cashback_result=None,
            utilization_score=0,
            status="uploading",
        ))

    initial_state: AnalysisState = {
        "session_id": session_id,
        "status": "uploading",
        "cards": cards,
        "current_card_idx": 0,
        "locked_card_idx": None,
        "locked_pdf_idx": None,
        "current_question": None,
        "comparison_result": None,
        "ui_action": "show_upload",
        "total_questions_count": 0,
        "answered_questions_count": 0,
        "error": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    final_state = await _run_graph(initial_state)
    return _state_to_response(final_state)


# ─────────────────────────────────────────────────────────────────────────────
# POST /session/{id}/password
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/{session_id}/password", response_model=SessionResponse)
async def submit_password(session_id: str, body: PasswordRequest):
    """
    Supply password for a locked PDF.

    Body: { password: string, card_idx: int }

    Resumes the graph after injecting the password into state.
    """
    state = await _load_session(session_id)
    if state is None:
        _raise_not_found(session_id)

    card_idx = body.card_idx
    if card_idx >= len(state.get("cards", [])):
        raise HTTPException(status_code=422, detail=f"card_idx {card_idx} out of range.")

    locked_pdf_idx = state.get("locked_pdf_idx") or 0

    # Inject password into the card's pdf_passwords list
    cards = deepcopy(state["cards"])
    passwords = list(cards[card_idx].get("pdf_passwords") or [])
    while len(passwords) <= locked_pdf_idx:
        passwords.append(None)
    passwords[locked_pdf_idx] = body.password
    cards[card_idx]["pdf_passwords"] = passwords

    state["cards"] = cards
    state["status"] = "uploading"  # Reset so pdf_check re-runs

    final_state = await _run_graph(state)
    return _state_to_response(final_state)


# ─────────────────────────────────────────────────────────────────────────────
# POST /session/{id}/answer
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/{session_id}/answer", response_model=SessionResponse)
async def submit_answer(session_id: str, body: AnswerRequest):
    """
    Submit a YES/NO answer for the current quiz question.

    Body: { question_id: string, answer: bool, card_idx: int }

    Resumes the graph from question_gen_node.
    """
    state = await _load_session(session_id)
    if state is None:
        _raise_not_found(session_id)

    card_idx = body.card_idx
    if card_idx >= len(state.get("cards", [])):
        raise HTTPException(status_code=422, detail=f"card_idx {card_idx} out of range.")

    # Inject answer into qa_answers
    cards = deepcopy(state["cards"])
    qa = dict(cards[card_idx].get("qa_answers") or {})
    qa[body.question_id] = body.answer
    cards[card_idx]["qa_answers"] = qa
    cards[card_idx]["status"] = "questioning"  # ensure card-level status matches

    state["cards"] = cards
    state["current_card_idx"] = card_idx
    state["status"] = "questioning"   # _run_graph will resume from question_gen_node
    state["error"] = None             # clear any previous error

    final_state = await _run_graph(state)
    return _state_to_response(final_state)


# ─────────────────────────────────────────────────────────────────────────────
# GET /session/{id}/status
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{session_id}/status", response_model=SessionResponse)
async def get_session_status(session_id: str):
    """
    Poll current session state without resuming the graph.
    Frontend polls every 2 s while ui_action == 'show_loading'.
    """
    state = await _load_session(session_id)
    if state is None:
        _raise_not_found(session_id)
    return _state_to_response(state)


# ─────────────────────────────────────────────────────────────────────────────
# POST /session/{id}/add_card
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/{session_id}/add_card", response_model=SessionResponse)
async def add_card(
    session_id: str,
    card_id: Annotated[str, Form()],
    pdf_files: Annotated[list[UploadFile], File()],
    month_labels: Annotated[list[str], Form()],
):
    """
    Add a new card + PDF(s) to an existing session.
    Triggers pdf_check for the new card only.
    """
    state = await _load_session(session_id)
    if state is None:
        _raise_not_found(session_id)

    if len(pdf_files) != len(month_labels):
        raise HTTPException(status_code=422, detail="pdf_files and month_labels must match.")

    # Look up card name
    card_name = card_id
    try:
        from db.connection import get_db
        db = get_db()
        doc = await db["credit_cards"].find_one({"_id": card_id}, {"name": 1})
        if doc:
            card_name = doc["name"]
    except Exception:
        pass

    pdf_contents = await _read_pdf_uploads(pdf_files)
    pairs = list(zip(pdf_contents, month_labels))
    new_card = CardState(
        card_id=card_id,
        card_name=card_name,
        months=[m for _, m in pairs],
        pdf_bytes_list=[b for b, _ in pairs],
        pdf_passwords=[None] * len(pairs),
        pdf_encrypted=False,
        pdf_text="",
        transactions=[],
        total_spend=0.0,
        pending_questions=[],
        answered_questions=[],
        qa_answers={},
        cashback_result=None,
        utilization_score=0,
        status="uploading",
    )

    cards = list(state.get("cards", []))
    cards.append(new_card)
    state["cards"] = cards
    state["current_card_idx"] = len(cards) - 1
    state["status"] = "uploading"

    final_state = await _run_graph(state)
    return _state_to_response(final_state)
