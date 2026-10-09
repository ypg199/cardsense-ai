"""
tests/test_security.py
─────────────────────────────────────────────────────────────────────────────
Security and data-handling tests: admin auth, upload limits, session
persistence (no stored passwords, TTL) and the encrypted-PDF unlock flow.
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
import io
import unittest.mock as mock
from datetime import datetime

import fitz
import pytest
from fastapi.testclient import TestClient

from agents.pdf_node import pdf_check_node
from api.routes import session as session_routes


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _pdf_bytes(text: str = "ZOMATO 450.00", password: str | None = None) -> bytes:
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), text)
    buf = io.BytesIO()
    if password:
        doc.save(buf, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw=password, owner_pw=password)
    else:
        doc.save(buf)
    doc.close()
    return buf.getvalue()


def _state(pdfs: list[bytes], status: str = "uploading") -> dict:
    return {
        "session_id": "sec-test",
        "status": status,
        "cards": [{
            "card_id": "axis-airtel",
            "card_name": "Axis Airtel",
            "months": [f"2024-0{i + 1}" for i in range(len(pdfs))],
            "pdf_bytes_list": list(pdfs),
            "pdf_passwords": [None] * len(pdfs),
            "pdf_encrypted": False,
            "pdf_text": "",
            "transactions": [],
            "total_spend": 0.0,
            "pending_questions": [],
            "answered_questions": [],
            "qa_answers": {},
            "cashback_result": None,
            "utilization_score": 0,
            "status": "uploading",
        }],
        "current_card_idx": 0,
        "locked_card_idx": None,
        "locked_pdf_idx": None,
        "current_question": None,
        "comparison_result": None,
        "ui_action": "show_upload",
        "total_questions_count": 0,
        "answered_questions_count": 0,
        "error": None,
        "created_at": "2024-01-01T00:00:00+00:00",
    }


class _FakeSessions:
    """In-memory stand-in for the Mongo `sessions` collection."""

    def __init__(self):
        self.docs: dict[str, dict] = {}

    async def replace_one(self, flt, doc, upsert=False):
        self.docs[flt["_id"]] = doc

    async def find_one(self, flt):
        doc = self.docs.get(flt["_id"])
        return dict(doc) if doc else None


@pytest.fixture
def fake_db():
    sessions = _FakeSessions()
    db = mock.MagicMock()
    db.__getitem__ = mock.MagicMock(return_value=sessions)
    with mock.patch("db.connection.get_db", return_value=db):
        yield sessions


def _save_then_load(state: dict) -> dict:
    asyncio.run(session_routes._save_session(state))
    return asyncio.run(session_routes._load_session(state["session_id"]))


def _submit_password(state: dict, password: str) -> dict:
    """Mirror POST /session/{id}/password: inject the password and re-check."""
    idx = state["locked_pdf_idx"]
    state["cards"][0]["pdf_passwords"][idx] = password
    state["status"] = "uploading"
    return {**state, **pdf_check_node(state)}


@pytest.fixture
def client():
    with mock.patch("db.connection.ping_db", return_value=True), \
         mock.patch("agents.graph.get_compiled_graph", return_value=None):
        from api.main import app
        yield TestClient(app, raise_server_exceptions=False)


# ─────────────────────────────────────────────────────────────────────────────
# Encrypted PDF unlock flow (regression: bytes were dropped on save)
# ─────────────────────────────────────────────────────────────────────────────

def test_locked_pdf_survives_save_and_unlocks(fake_db):
    state = _state([_pdf_bytes(password="secret")])
    state = {**state, **pdf_check_node(state)}
    assert state["status"] == "pdf_locked"

    state = _save_then_load(state)
    assert state["cards"][0]["pdf_bytes_list"], "encrypted PDF must be kept while locked"

    state = _submit_password(state, "secret")
    assert state["status"] == "parsing"
    assert "ZOMATO" in state["cards"][0]["pdf_text"]


def test_second_locked_pdf_does_not_reask_first(fake_db):
    state = _state([_pdf_bytes(password="jan"), _pdf_bytes("AMAZON 1200", password="feb")])
    state = {**state, **pdf_check_node(state)}
    assert state["locked_pdf_idx"] == 0

    state = _submit_password(_save_then_load(state), "jan")
    assert state["status"] == "pdf_locked"
    assert state["locked_pdf_idx"] == 1

    state = _submit_password(_save_then_load(state), "feb")
    assert state["status"] == "parsing"
    assert "AMAZON" in state["cards"][0]["pdf_text"]


def test_wrong_password_keeps_session_recoverable(fake_db):
    state = _state([_pdf_bytes(password="secret")])
    state = {**state, **pdf_check_node(state)}
    state = _submit_password(_save_then_load(state), "nope")
    assert state["status"] == "pdf_locked"
    assert state["error"]

    state = _submit_password(_save_then_load(state), "secret")
    assert state["status"] == "parsing"


# ─────────────────────────────────────────────────────────────────────────────
# Session persistence
# ─────────────────────────────────────────────────────────────────────────────

def test_passwords_are_never_persisted(fake_db):
    state = _state([_pdf_bytes(password="secret")])
    state["cards"][0]["pdf_passwords"] = ["secret"]
    asyncio.run(session_routes._save_session(state))
    assert fake_db.docs["sec-test"]["cards"][0]["pdf_passwords"] == [None]


def test_pdf_bytes_dropped_once_unlocked(fake_db):
    state = _state([_pdf_bytes()])
    state["cards"][0]["status"] = "parsing"
    asyncio.run(session_routes._save_session(state))
    assert fake_db.docs["sec-test"]["cards"][0]["pdf_bytes_list"] == []


def test_session_has_expiry_date(fake_db):
    asyncio.run(session_routes._save_session(_state([_pdf_bytes()])))
    assert isinstance(fake_db.docs["sec-test"]["expires_at"], datetime)


# ─────────────────────────────────────────────────────────────────────────────
# Upload validation
# ─────────────────────────────────────────────────────────────────────────────

def _upload(client, content: bytes, filename: str = "s.pdf"):
    return client.post(
        "/session/start",
        data={"card_ids": ["axis-airtel"], "month_labels": ["2024-01"]},
        files=[("pdf_files", (filename, io.BytesIO(content), "application/pdf"))],
    )


def test_non_pdf_upload_rejected(client):
    r = _upload(client, b"MZ\x90\x00 not a pdf", "evil.pdf")
    assert r.status_code == 422
    assert "not a PDF" in r.json()["detail"]


def test_oversized_upload_rejected(client):
    with mock.patch.object(session_routes, "MAX_UPLOAD_BYTES", 100):
        r = _upload(client, b"%PDF-1.4" + b"0" * 200)
    assert r.status_code == 413


def test_too_many_files_rejected(client):
    with mock.patch.object(session_routes, "MAX_FILES_PER_REQUEST", 1):
        r = client.post(
            "/session/start",
            data={"card_ids": ["a"], "month_labels": ["2024-01", "2024-02"]},
            files=[("pdf_files", ("a.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf"))] * 2,
        )
    assert r.status_code == 422


def test_negative_card_idx_rejected(client):
    r = client.post("/session/x/answer", json={"question_id": "q", "answer": True, "card_idx": -1})
    assert r.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# Admin auth on /crawl
# ─────────────────────────────────────────────────────────────────────────────

def test_crawl_disabled_without_admin_key(client):
    with mock.patch("api.settings.ADMIN_API_KEY", ""):
        assert client.post("/crawl", json={}).status_code == 403
        assert client.get("/crawl/jobs").status_code == 403


def test_crawl_rejects_wrong_admin_key(client):
    with mock.patch("api.settings.ADMIN_API_KEY", "right"):
        r = client.post("/crawl", json={}, headers={"X-Admin-Key": "wrong"})
    assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Card search
# ─────────────────────────────────────────────────────────────────────────────

def test_search_regex_input_is_escaped(client):
    seen = {}

    class _Cursor:
        def sort(self, *a, **kw):
            return self

        def limit(self, *a):
            return self

        async def to_list(self, length):
            return []

    def _find(query, projection=None):
        if "$text" in query:
            raise RuntimeError("no text index")
        seen["query"] = query
        return _Cursor()

    col = mock.MagicMock()
    col.find = _find
    db = mock.MagicMock()
    db.__getitem__ = mock.MagicMock(return_value=col)

    with mock.patch("db.connection.get_db", return_value=db):
        r = client.get("/cards/search", params={"q": "(a+)+$"})

    assert r.status_code == 200
    assert seen["query"]["$or"][0]["name"]["$regex"] == r"\(a\+\)\+\$"
