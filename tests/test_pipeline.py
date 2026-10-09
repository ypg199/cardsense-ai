"""
tests/test_pipeline.py
─────────────────────────────────────────────────────────────────────────────
_run_graph orchestration: every uploaded card is analysed before the
cross-card comparison runs.
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
import unittest.mock as mock

from api.routes import session as session_routes


def _card(card_id: str) -> dict:
    return {"card_id": card_id, "card_name": card_id, "status": "uploading", "pdf_bytes_list": [b"%PDF-1.4"]}


def _state(n_cards: int) -> dict:
    return {
        "session_id": "pipe",
        "status": "uploading",
        "cards": [_card(f"card-{i}") for i in range(n_cards)],
        "current_card_idx": 0,
        "ui_action": "show_upload",
        "error": None,
    }


class _FakeNodes:
    """Stand-ins for the agent nodes that record which card each one saw."""

    def __init__(self, locked: set[int] = frozenset()):
        self.calls: list[tuple[str, int]] = []
        self.locked = set(locked)

    def _set_card(self, state, status):
        cards = [dict(c) for c in state["cards"]]
        cards[state["current_card_idx"]]["status"] = status
        return cards

    def pdf_check(self, state):
        idx = state["current_card_idx"]
        self.calls.append(("pdf", idx))
        if idx in self.locked:
            return {
                "cards": self._set_card(state, "pdf_locked"),
                "status": "pdf_locked",
                "ui_action": "show_password_input",
            }
        return {"cards": self._set_card(state, "parsing"), "status": "parsing"}

    async def parse(self, state):
        self.calls.append(("parse", state["current_card_idx"]))
        return {"cards": self._set_card(state, "questioning"), "status": "questioning"}

    async def questions(self, state):
        self.calls.append(("questions", state["current_card_idx"]))
        return {"status": "calculating", "ui_action": "show_loading"}

    async def cashback(self, state):
        self.calls.append(("cashback", state["current_card_idx"]))
        return {"cards": self._set_card(state, "comparing"), "status": "comparing"}

    async def compare(self, state):
        self.calls.append(("compare", state["current_card_idx"]))
        return {"status": "done", "ui_action": "show_results"}

    def patches(self):
        return [
            mock.patch("agents.pdf_node.pdf_check_node", self.pdf_check),
            mock.patch("agents.parse_node.parse_transactions_node", self.parse),
            mock.patch("agents.question_node.question_gen_node", self.questions),
            mock.patch("agents.cashback_node.cashback_calc_node", self.cashback),
            mock.patch("agents.compare_node.compare_node", self.compare),
            mock.patch.object(session_routes, "_save_session", mock.AsyncMock()),
        ]


def _run(nodes: _FakeNodes, state: dict) -> dict:
    ps = nodes.patches()
    for p in ps:
        p.start()
    try:
        return asyncio.run(session_routes._run_graph(state))
    finally:
        for p in ps:
            p.stop()


def test_every_card_is_analysed_before_compare():
    nodes = _FakeNodes()
    result = _run(nodes, _state(2))

    assert result["status"] == "done"
    assert ("cashback", 0) in nodes.calls and ("cashback", 1) in nodes.calls
    assert nodes.calls[-1][0] == "compare"
    assert [c for c in nodes.calls if c[0] == "compare"] == [("compare", 1)]


def test_locked_second_card_pauses_on_that_card():
    nodes = _FakeNodes(locked={1})
    result = _run(nodes, _state(2))

    assert result["status"] == "pdf_locked"
    assert result["current_card_idx"] == 1
    assert ("cashback", 0) in nodes.calls
    assert not any(c[0] == "compare" for c in nodes.calls)


def test_single_card_unchanged():
    nodes = _FakeNodes()
    result = _run(nodes, _state(1))
    assert result["status"] == "done"
    assert [c[0] for c in nodes.calls] == ["pdf", "parse", "questions", "cashback", "compare"]


def test_unprocessed_card_keeps_pdf_bytes_on_save():
    state = _state(2)
    state["cards"][0]["status"] = "questioning"
    saved = {}

    class _Col:
        async def replace_one(self, flt, doc, upsert=False):
            saved.update(doc)

    db = mock.MagicMock()
    db.__getitem__ = mock.MagicMock(return_value=_Col())
    with mock.patch("db.connection.get_db", return_value=db):
        asyncio.run(session_routes._save_session(state))

    assert saved["cards"][0]["pdf_bytes_list"] == []
    assert saved["cards"][1]["pdf_bytes_list"] == [b"%PDF-1.4"]
