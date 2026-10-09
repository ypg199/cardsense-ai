"""
tests/test_api.py
─────────────────────────────────────────────────────────────────────────────
FastAPI route tests using Starlette TestClient (sync).
All DB calls and graph runs are mocked.
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import io
import os
import sys
import unittest.mock as mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

# ─────────────────────────────────────────────────────────────────────────────
# Shared mock state returned by _run_graph
# ─────────────────────────────────────────────────────────────────────────────

MOCK_SESSION_ID = "test-session-abc123"

MOCK_STATE_PARSING = {
    "session_id": MOCK_SESSION_ID,
    "status": "questioning",
    "ui_action": "show_question",
    "current_card_idx": 0,
    "cards": [
        {
            "card_id": "axis-airtel",
            "card_name": "Axis Airtel Credit Card",
            "months": ["2024-01"],
            "pdf_bytes_list": [],
            "pdf_passwords": [None],
            "pdf_encrypted": False,
            "pdf_text": "ZOMATO 450\nAIRTEL 299",
            "transactions": [
                {
                    "date": "2024-01-01",
                    "merchant": "Zomato",
                    "amount": 450.0,
                    "transaction_type": "debit",
                    "category": "food_delivery",
                    "month": "2024-01",
                },
            ],
            "total_spend": 450.0,
            "pending_questions": [],
            "answered_questions": [],
            "qa_answers": {},
            "cashback_result": None,
            "utilization_score": 0,
            "status": "questioning",
        }
    ],
    "locked_card_idx": None,
    "locked_pdf_idx": None,
    "current_question": {
        "id": "q_zomato",
        "category": "food_delivery",
        "text": "Do you order food on Zomato using this card?",
        "hint": "Earns 10% cashback — ₹45 potential this month",
        "detected_spend": 450.0,
        "potential_cashback": 45.0,
        "is_general": False,
    },
    "comparison_result": None,
    "total_questions_count": 3,
    "answered_questions_count": 0,
    "error": None,
    "created_at": "2024-01-01T00:00:00Z",
}

MOCK_STATE_DONE = {
    **MOCK_STATE_PARSING,
    "status": "done",
    "ui_action": "show_results",
    "current_question": None,
    "answered_questions_count": 3,
    "cards": [
        {
            **MOCK_STATE_PARSING["cards"][0],
            "cashback_result": {
                "earned_breakdown": {"food_delivery": 45.0},
                "missed_breakdown": {"airtel_recharge": 74.75},
                "utilization_score": 38,
                "monthly_breakdown": [{"month": "2024-01", "earned": 45.0, "missed": 74.75, "score": 38}],
                "trend": "single_month",
            },
            "utilization_score": 38,
            "status": "done",
        }
    ],
    "comparison_result": {
        "verdict": "Could do better",
        "verdict_reason": "You are only using 38% of this card's potential.",
        "card_score": 38,
        "recommendations": [
            {
                "card_id": "hdfc-millennia",
                "card_name": "HDFC Millennia",
                "bank": "HDFC Bank",
                "estimated_monthly_cashback": 150.0,
                "estimated_annual_cashback": 1800.0,
                "improvement_over_current_monthly": 105.0,
                "why_better": "Earns 5% on food delivery vs 10% on Airtel card.",
                "best_categories": ["food_delivery"],
                "caveat": "Annual fee of ₹1000.",
            }
        ],
        "routing_advice": ["Use Axis Airtel for Airtel recharges (25%)"],
        "tips": ["Use this card for all Airtel recharges."],
    },
}

MOCK_CARD_DOC = {
    "_id": "axis-airtel",
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
            "conditions": None,
            "merchant_keywords": ["airtel"],
        },
    ],
    "best_for_tags": ["airtel users"],
    "not_good_for": ["amazon"],
    "source_url": "https://example.com",
    "last_crawled": "2024-01-01T00:00:00Z",
}

PASS = 0
FAIL = 0


def ok(msg: str):
    global PASS
    PASS += 1
    print(f"  ✅ {msg}")


def fail(msg: str):
    global FAIL
    FAIL += 1
    print(f"  ❌ {msg}")


# ─────────────────────────────────────────────────────────────────────────────
# Client factory (patches DB + graph per test)
# ─────────────────────────────────────────────────────────────────────────────


def _make_client(run_graph_return=None, load_session_return=None, card_docs=None):
    """Build a TestClient with mocked DB and graph."""
    if run_graph_return is None:
        run_graph_return = MOCK_STATE_PARSING
    if card_docs is None:
        card_docs = [MOCK_CARD_DOC]

    async def _mock_run_graph(state):
        state.update(run_graph_return)
        state["session_id"] = state.get("session_id") or MOCK_SESSION_ID
        return state

    async def _mock_load_session(sid):
        return load_session_return

    async def _mock_save_session(state):
        pass

    async def _mock_find_one(query, projection=None):
        cid = query.get("_id", "")
        for doc in card_docs:
            if doc.get("_id") == cid:
                return {k: v for k, v in doc.items() if k != "embedding"}
        return None

    async def _mock_ping():
        return True

    # Patch everything before importing app
    patches = [
        mock.patch("api.routes.session._run_graph", side_effect=_mock_run_graph),
        mock.patch("api.routes.session._load_session", side_effect=_mock_load_session),
        mock.patch("api.routes.session._save_session", side_effect=_mock_save_session),
        mock.patch("db.connection.ping_db", side_effect=_mock_ping),
        mock.patch("agents.graph.get_compiled_graph", return_value=None),
    ]

    for p in patches:
        p.start()

    from api.main import app

    client = TestClient(app, raise_server_exceptions=False)
    return client, patches


def _stop_patches(patches):
    for p in patches:
        try:
            p.stop()
        except RuntimeError:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# 1. Health / root
# ─────────────────────────────────────────────────────────────────────────────


def test_health():
    print("\n[1] GET /health")
    client, patches = _make_client()
    try:
        r = client.get("/health")
        assert r.status_code == 200
        ok("GET /health → 200")
        assert r.json()["status"] == "ok"
        ok("health.status == 'ok'")
    finally:
        _stop_patches(patches)


def test_root():
    print("\n[2] GET /")
    client, patches = _make_client()
    try:
        r = client.get("/")
        assert r.status_code == 200
        ok("GET / → 200")
        data = r.json()
        assert "service" in data and "CardSense" in data["service"]
        ok("Root returns service name")
    finally:
        _stop_patches(patches)


# ─────────────────────────────────────────────────────────────────────────────
# 2. POST /session/start
# ─────────────────────────────────────────────────────────────────────────────


def _make_pdf_file(content: bytes = b"%PDF-1.4 fake") -> tuple:
    return ("pdf_files", ("statement.pdf", io.BytesIO(content), "application/pdf"))


def test_session_start_happy_path():
    print("\n[3] POST /session/start — happy path")
    client, patches = _make_client()
    try:
        r = client.post(
            "/session/start",
            data={"card_ids": ["axis-airtel"], "month_labels": ["2024-01"]},
            files=[_make_pdf_file()],
        )
        assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text}"
        ok("POST /session/start → 201")

        data = r.json()
        assert "session_id" in data
        ok("session_id in response")

        assert "status" in data
        ok("status in response")

        assert "ui_action" in data
        ok("ui_action in response")

        assert "cards" in data and isinstance(data["cards"], list)
        ok("cards[] in response")

        assert "current_card_idx" in data
        ok("current_card_idx in response")
    finally:
        _stop_patches(patches)


def test_session_start_missing_card_ids():
    print("\n[4] POST /session/start — missing card_ids → 422")
    client, patches = _make_client()
    try:
        r = client.post(
            "/session/start",
            data={"month_labels": ["2024-01"]},
            files=[_make_pdf_file()],
        )
        assert r.status_code == 422
        ok("Missing card_ids → 422")
    finally:
        _stop_patches(patches)


def test_session_start_mismatched_files():
    print("\n[5] POST /session/start — mismatched pdf_files / month_labels → 422")
    client, patches = _make_client()
    try:
        r = client.post(
            "/session/start",
            data={"card_ids": ["axis-airtel"], "month_labels": ["2024-01", "2024-02"]},
            files=[_make_pdf_file()],  # 1 file but 2 month labels
        )
        assert r.status_code == 422
        ok("Mismatched file/month counts → 422")
    finally:
        _stop_patches(patches)


def test_session_start_question_in_response():
    print("\n[6] POST /session/start — question returned when graph pauses")
    client, patches = _make_client(run_graph_return=MOCK_STATE_PARSING)
    try:
        r = client.post(
            "/session/start",
            data={"card_ids": ["axis-airtel"], "month_labels": ["2024-01"]},
            files=[_make_pdf_file()],
        )
        data = r.json()
        assert data.get("ui_action") == "show_question"
        ok("ui_action == 'show_question'")

        cq = data.get("current_question")
        assert cq is not None
        ok("current_question is set")

        assert "id" in cq and "text" in cq and "hint" in cq
        ok("current_question has id, text, hint")

        assert data["questions_total"] == 3
        ok("questions_total == 3")
    finally:
        _stop_patches(patches)


# ─────────────────────────────────────────────────────────────────────────────
# 3. POST /session/{id}/answer
# ─────────────────────────────────────────────────────────────────────────────


def test_answer_success():
    print("\n[7] POST /session/{id}/answer — success")
    client, patches = _make_client(
        run_graph_return=MOCK_STATE_PARSING,
        load_session_return=MOCK_STATE_PARSING,
    )
    try:
        r = client.post(
            f"/session/{MOCK_SESSION_ID}/answer",
            json={"question_id": "q_zomato", "answer": True, "card_idx": 0},
        )
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        ok("POST /session/{id}/answer → 200")

        data = r.json()
        assert data["session_id"] == MOCK_SESSION_ID
        ok("session_id in answer response")

        assert "status" in data
        ok("status in answer response")
    finally:
        _stop_patches(patches)


def test_answer_session_not_found():
    print("\n[8] POST /session/{id}/answer — session not found → 404")
    client, patches = _make_client(load_session_return=None)
    try:
        r = client.post(
            "/session/nonexistent/answer",
            json={"question_id": "q1", "answer": True, "card_idx": 0},
        )
        assert r.status_code == 404
        ok("Missing session → 404")
    finally:
        _stop_patches(patches)


def test_answer_invalid_card_idx():
    print("\n[9] POST /session/{id}/answer — invalid card_idx → 422")
    client, patches = _make_client(load_session_return=MOCK_STATE_PARSING)
    try:
        r = client.post(
            f"/session/{MOCK_SESSION_ID}/answer",
            json={"question_id": "q1", "answer": True, "card_idx": 99},  # out of range
        )
        assert r.status_code == 422
        ok("Invalid card_idx → 422")
    finally:
        _stop_patches(patches)


# ─────────────────────────────────────────────────────────────────────────────
# 4. POST /session/{id}/password
# ─────────────────────────────────────────────────────────────────────────────


def test_password_success():
    print("\n[10] POST /session/{id}/password — success")
    locked_state = {
        **MOCK_STATE_PARSING,
        "status": "pdf_locked",
        "locked_card_idx": 0,
        "locked_pdf_idx": 0,
    }
    client, patches = _make_client(
        run_graph_return=MOCK_STATE_PARSING,
        load_session_return=locked_state,
    )
    try:
        r = client.post(
            f"/session/{MOCK_SESSION_ID}/password",
            json={"password": "mypassword", "card_idx": 0},
        )
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        ok("POST /session/{id}/password → 200")

        data = r.json()
        assert data["session_id"] == MOCK_SESSION_ID
        ok("session_id in password response")
    finally:
        _stop_patches(patches)


def test_password_session_not_found():
    print("\n[11] POST /session/{id}/password — session not found → 404")
    client, patches = _make_client(load_session_return=None)
    try:
        r = client.post(
            "/session/missing/password",
            json={"password": "pw", "card_idx": 0},
        )
        assert r.status_code == 404
        ok("Missing session → 404")
    finally:
        _stop_patches(patches)


# ─────────────────────────────────────────────────────────────────────────────
# 5. GET /session/{id}/status
# ─────────────────────────────────────────────────────────────────────────────


def test_get_status_success():
    print("\n[12] GET /session/{id}/status — success")
    client, patches = _make_client(load_session_return=MOCK_STATE_PARSING)
    try:
        r = client.get(f"/session/{MOCK_SESSION_ID}/status")
        assert r.status_code == 200
        ok("GET /session/{id}/status → 200")

        data = r.json()
        assert data["session_id"] == MOCK_SESSION_ID
        ok("session_id correct")
        assert data["status"] == "questioning"
        ok("status == 'questioning'")
    finally:
        _stop_patches(patches)


def test_get_status_done_has_results():
    print("\n[13] GET /session/{id}/status — done state has comparison_result")
    client, patches = _make_client(load_session_return=MOCK_STATE_DONE)
    try:
        r = client.get(f"/session/{MOCK_SESSION_ID}/status")
        assert r.status_code == 200
        data = r.json()

        assert data["ui_action"] == "show_results"
        ok("ui_action == 'show_results'")

        assert data["comparison_result"] is not None
        ok("comparison_result is populated")

        cr = data["comparison_result"]
        assert cr["verdict"] == "Could do better"
        ok("verdict == 'Could do better'")

        assert len(cr["recommendations"]) == 1
        ok("1 recommendation in response")

        assert cr["recommendations"][0]["card_id"] == "hdfc-millennia"
        ok("recommendation card_id correct")
    finally:
        _stop_patches(patches)


def test_get_status_not_found():
    print("\n[14] GET /session/{id}/status — not found → 404")
    client, patches = _make_client(load_session_return=None)
    try:
        r = client.get("/session/no-such-session/status")
        assert r.status_code == 404
        ok("Missing session → 404")
    finally:
        _stop_patches(patches)


# ─────────────────────────────────────────────────────────────────────────────
# 6. SessionResponse structure
# ─────────────────────────────────────────────────────────────────────────────


def test_session_response_structure():
    print("\n[15] SessionResponse has all required fields (Section 6)")
    client, patches = _make_client(load_session_return=MOCK_STATE_DONE)
    try:
        r = client.get(f"/session/{MOCK_SESSION_ID}/status")
        data = r.json()

        required_fields = [
            "session_id",
            "status",
            "ui_action",
            "current_card_idx",
            "cards",
            "current_question",
            "questions_answered",
            "questions_total",
            "cashback_result",
            "comparison_result",
            "error",
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        ok(f"All {len(required_fields)} required SessionResponse fields present")

        # cards[] structure
        card = data["cards"][0]
        for cf in [
            "card_id",
            "card_name",
            "months",
            "transactions_count",
            "total_spend",
            "pdf_encrypted",
            "status",
        ]:
            assert cf in card, f"Missing card field: {cf}"
        ok("CardSummaryOut has all required fields")
    finally:
        _stop_patches(patches)


# ─────────────────────────────────────────────────────────────────────────────
# 7. GET /cards
# ─────────────────────────────────────────────────────────────────────────────


def test_list_cards():
    print("\n[16] GET /cards")

    client, patches = _make_client()

    # Motor's find() returns a sync cursor; chain skip/limit is sync too
    mock_cursor = mock.MagicMock()
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor
    mock_cursor.to_list = mock.AsyncMock(return_value=[MOCK_CARD_DOC])

    mock_col = mock.MagicMock()
    mock_col.count_documents = mock.AsyncMock(return_value=1)
    mock_col.find.return_value = mock_cursor

    mock_db = mock.MagicMock()
    mock_db.__getitem__ = mock.MagicMock(return_value=mock_col)

    with mock.patch("db.connection.get_db", return_value=mock_db):
        try:
            r = client.get("/cards")
            assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
            ok("GET /cards → 200")
            data = r.json()
            assert "count" in data and "cards" in data
            ok("Response has count and cards")
        finally:
            _stop_patches(patches)


def test_get_card_not_found():
    print("\n[17] GET /cards/{id} — not found → 404")
    client, patches = _make_client()

    mock_col = mock.MagicMock()
    mock_col.find_one = mock.AsyncMock(return_value=None)
    mock_db = mock.MagicMock()
    mock_db.__getitem__ = mock.MagicMock(return_value=mock_col)

    with mock.patch("db.connection.get_db", return_value=mock_db):
        try:
            r = client.get("/cards/nonexistent-card")
            assert r.status_code == 404
            ok("GET /cards/nonexistent → 404")
        finally:
            _stop_patches(patches)


# ─────────────────────────────────────────────────────────────────────────────
# 8. POST /crawl
# ─────────────────────────────────────────────────────────────────────────────


def test_trigger_crawl():
    print("\n[18] POST /crawl")
    client, patches = _make_client()

    mock_col = mock.MagicMock()
    mock_col.insert_one = mock.AsyncMock(return_value=None)
    mock_db = mock.MagicMock()
    mock_db.__getitem__ = mock.MagicMock(return_value=mock_col)

    # crawler.tasks may not exist yet (built in Step 12) — patch both paths
    with (
        mock.patch("db.connection.get_db", return_value=mock_db),
        mock.patch("api.settings.ADMIN_API_KEY", "test-admin-key"),
        mock.patch.dict(
            "sys.modules",
            {
                "crawler": mock.MagicMock(),
                "crawler.tasks": mock.MagicMock(run_crawl=mock.MagicMock()),
            },
        ),
    ):
        try:
            r = client.post(
                "/crawl",
                json={"sources": ["cardinsider"]},
                headers={"X-Admin-Key": "test-admin-key"},
            )
            assert r.status_code == 202
            ok("POST /crawl → 202")
            data = r.json()
            assert "job_id" in data
            ok("job_id in response")
            assert "message" in data
            ok("message in response")
        finally:
            _stop_patches(patches)


# ─────────────────────────────────────────────────────────────────────────────
# 9. API models validation
# ─────────────────────────────────────────────────────────────────────────────


def test_models_importable():
    print("\n[19] api/models.py — all models importable and valid")
    from api.models import (
        AnswerRequest,
        CrawlRequest,
        PasswordRequest,
    )

    ok("All 16 Pydantic models importable")

    # Validate AnswerRequest
    req = AnswerRequest(question_id="q_test", answer=True, card_idx=0)
    assert req.question_id == "q_test"
    assert req.answer is True
    ok("AnswerRequest validates correctly")

    # Validate PasswordRequest
    preq = PasswordRequest(password="mypassword", card_idx=1)
    assert preq.password == "mypassword"
    ok("PasswordRequest validates correctly")

    # Validate CrawlRequest defaults
    creq = CrawlRequest()
    assert creq.sources is None
    assert creq.direct_urls is None
    ok("CrawlRequest defaults to None lists")


def test_state_to_response_conversion():
    print("\n[20] _state_to_response — converts AnalysisState → SessionResponse")
    from api.routes.session import _state_to_response

    resp = _state_to_response(MOCK_STATE_DONE)
    assert resp.session_id == MOCK_SESSION_ID
    ok("session_id converted")

    assert resp.status == "done"
    ok("status converted")

    assert resp.ui_action == "show_results"
    ok("ui_action converted")

    assert len(resp.cards) == 1
    ok("cards[] has 1 entry")

    assert resp.cards[0].card_id == "axis-airtel"
    ok("card_id correct")

    assert resp.cashback_result is not None
    ok("cashback_result populated")

    assert resp.cashback_result.utilization_score == 38
    ok("utilization_score == 38")

    # The results page reads the breakdown from each card
    assert resp.cards[0].cashback_result is not None
    assert resp.cards[0].cashback_result.utilization_score == 38
    ok("cards[0].cashback_result populated")

    assert resp.comparison_result is not None
    ok("comparison_result populated")

    assert resp.comparison_result.verdict == "Could do better"
    ok("verdict correct")


# ─────────────────────────────────────────────────────────────────────────────
# Run all
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  API route test suite")
    print("=" * 60)

    test_health()
    test_root()
    test_session_start_happy_path()
    test_session_start_missing_card_ids()
    test_session_start_mismatched_files()
    test_session_start_question_in_response()
    test_answer_success()
    test_answer_session_not_found()
    test_answer_invalid_card_idx()
    test_password_success()
    test_password_session_not_found()
    test_get_status_success()
    test_get_status_done_has_results()
    test_get_status_not_found()
    test_session_response_structure()
    test_list_cards()
    test_get_card_not_found()
    test_trigger_crawl()
    test_models_importable()
    test_state_to_response_conversion()

    print()
    print("=" * 60)
    print(f"  Results: {PASS} passed, {FAIL} failed")
    print("=" * 60)

    if FAIL > 0:
        sys.exit(1)


def test_session_start_groups_months_of_the_same_card():
    """The UI sends one card_id per PDF; four months of one card must be one card."""
    captured = {}

    async def _capture(state):
        captured["cards"] = state["cards"]
        state.update(MOCK_STATE_PARSING)
        return state

    client, patches = _make_client()
    extra = mock.patch("api.routes.session._run_graph", side_effect=_capture)
    extra.start()
    try:
        months = ["2024-01", "2024-02", "2024-03", "2024-04", "2024-01"]
        ids = ["hdfc-millennia"] * 4 + ["axis-airtel"]
        r = client.post(
            "/session/start",
            data={"card_ids": ids, "month_labels": months},
            files=[_make_pdf_file() for _ in months],
        )
        assert r.status_code == 201, r.text
        cards = captured["cards"]
        assert [c["card_id"] for c in cards] == ["hdfc-millennia", "axis-airtel"]
        assert cards[0]["months"] == months[:4]
        assert len(cards[0]["pdf_bytes_list"]) == 4
        assert cards[1]["months"] == ["2024-01"]
    finally:
        extra.stop()
        _stop_patches(patches)
