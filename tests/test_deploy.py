"""Deployment safeguards: the per-client rate limit and the card catalogue copy."""

from __future__ import annotations

from pymongo import ReplaceOne

from api import rate_limit, settings
from db.copy_cards import copy_cards
from tests.test_api import _make_client, _stop_patches


def test_rate_limit_returns_429_after_the_hourly_allowance(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_HOUR", 2)
    rate_limit.reset()
    client, patches = _make_client()
    try:
        codes = [client.post("/session/sample", json={"mode": "spend"}).status_code for _ in range(3)]
        assert codes == [201, 201, 429]
        r = client.post("/session/sample", json={"mode": "spend"})
        assert int(r.headers["Retry-After"]) > 0
        assert "try again" in r.json()["detail"]
    finally:
        _stop_patches(patches)
        rate_limit.reset()


def test_rate_limit_is_off_by_default():
    rate_limit.reset()
    assert settings.RATE_LIMIT_PER_HOUR == 0
    client, patches = _make_client()
    try:
        for _ in range(5):
            assert client.post("/session/sample", json={"mode": "spend"}).status_code == 201
    finally:
        _stop_patches(patches)


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = {d["_id"]: d for d in docs or []}

    def find(self):
        return list(self.docs.values())

    def bulk_write(self, ops: list[ReplaceOne], ordered: bool = True):
        for op in ops:
            doc = op._doc
            self.docs[doc["_id"]] = doc


def test_copy_cards_upserts_every_card_in_batches():
    source = _FakeCollection(
        [{"_id": f"card-{i}", "name": f"Card {i}", "embedding": [0.1] * 3} for i in range(250)]
    )
    target = _FakeCollection([{"_id": "card-0", "name": "Stale"}, {"_id": "other", "name": "Kept"}])

    assert copy_cards(source, target) == 250
    assert len(target.docs) == 251
    assert target.docs["card-0"]["name"] == "Card 0"
    assert target.docs["card-249"]["embedding"] == [0.1] * 3
    assert target.docs["other"]["name"] == "Kept"
    # Running it again changes nothing
    assert copy_cards(source, target) == 250
    assert len(target.docs) == 251
