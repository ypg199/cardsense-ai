"""
db/dedupe_cards.py
─────────────────────────────────────────────────────────────────────────────
Find credit cards stored more than once and, if asked, remove the extra copies.

Two records count as the same card when their bank and name give the same
card key ("Axis Bank" / "Flipkart Axis Bank Credit Card" and "Axis" /
"Flipkart" are both "axis-flipkart"). In each
group the most complete record is kept: crawled from the bank's site, with an
embedding, the most benefits, crawled most recently.

Names that only look alike (one name's words all appear in the other's, e.g.
"Regalia" and "Regalia Gold") and different names stored from the same page
are listed for a look but never removed.

Usage:
    python -m db.dedupe_cards                 # report only, changes nothing
    python -m db.dedupe_cards --apply         # delete the extra copies
    python -m db.dedupe_cards --uri "mongodb+srv://..."   # default: MONGODB_URI
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import os
from collections import defaultdict
from itertools import combinations

from dotenv import load_dotenv

from db.card_keys import bank_key, card_key

COLLECTION = "credit_cards"
FIELDS = {
    "_id": 1,
    "name": 1,
    "bank": 1,
    "source_url": 1,
    "content_hash": 1,
    "last_crawled": 1,
    "benefits": 1,
    "embedding": {"$slice": 1},
}


def _rank(doc: dict) -> tuple:
    """Higher is better: crawled, has a vector, more benefits, newer."""
    return (
        "content_hash" in doc,
        bool(doc.get("embedding")),
        len(doc.get("benefits") or []),
        str(doc.get("last_crawled") or ""),
        # Prefer the id the crawler would give it today, then a stable order
        doc["_id"] == card_key(doc.get("bank", ""), doc.get("name", "")),
        str(doc["_id"]),
    )


def find_duplicates(docs: list[dict]) -> list[dict]:
    """
    Group records with the same card key. Returns one entry per group of two
    or more: {"key", "keep": doc, "remove": [doc, ...]}, keepers ranked first.
    """
    groups: dict[str, list[dict]] = defaultdict(list)
    for d in docs:
        groups[card_key(d.get("bank", ""), d.get("name", ""))].append(d)

    result = []
    for key, members in sorted(groups.items()):
        if len(members) < 2:
            continue
        members.sort(key=_rank, reverse=True)
        result.append({"key": key, "keep": members[0], "remove": members[1:]})
    return result


def _page(url: str) -> str:
    """A page address compared as stored, ignoring only a trailing slash."""
    return (url or "").strip().rstrip("/").lower()


def find_lookalikes(docs: list[dict]) -> list[tuple[dict, dict]]:
    """
    Pairs worth a look but never removed: cards at the same bank where one card
    key's words are all in the other's, and cards with different keys stored
    from the same page (an older crawler could save several cards per page).
    """
    by_bank: dict[str, list[tuple[set[str], dict]]] = defaultdict(list)
    by_page: dict[str, list[dict]] = defaultdict(list)
    for d in docs:
        key = card_key(d.get("bank", ""), d.get("name", ""))
        by_bank[bank_key(d.get("bank", ""))].append((set(key.split("-")[1:]), d))
        if d.get("source_url"):
            by_page[_page(d["source_url"])].append(d)
    pairs = []
    for cards in by_bank.values():
        for (wa, a), (wb, b) in combinations(cards, 2):
            if wa and wb and wa != wb and (wa < wb or wb < wa):
                pairs.append((a, b))
    seen = {(a["_id"], b["_id"]) for a, b in pairs}
    for cards in by_page.values():
        for a, b in combinations(cards, 2):
            same_key = card_key(a.get("bank", ""), a.get("name", "")) == card_key(
                b.get("bank", ""), b.get("name", "")
            )
            if not same_key and (a["_id"], b["_id"]) not in seen:
                pairs.append((a, b))
    return pairs


def _line(doc: dict) -> str:
    crawled = "crawled" if "content_hash" in doc else "not crawled"
    return (
        f"{doc['_id']:<40} {doc.get('name', '')!s:<45} {crawled}, {len(doc.get('benefits') or [])} benefits"
    )


def report(docs: list[dict], groups: list[dict], lookalikes: list[tuple[dict, dict]]) -> str:
    extra = sum(len(g["remove"]) for g in groups)
    lines = [f"{len(docs)} cards stored, {len(docs) - extra} unique, {extra} duplicate records", ""]
    by_bank: dict[str, int] = defaultdict(int)
    for d in docs:
        by_bank[d.get("bank") or "?"] += 1
    lines.append("By bank: " + ", ".join(f"{b} {n}" for b, n in sorted(by_bank.items())))
    lines.append("")
    if groups:
        lines.append("Duplicates (removed with --apply):")
        for g in groups:
            lines.append(f"  keep    {_line(g['keep'])}")
            for d in g["remove"]:
                lines.append(f"  remove  {_line(d)}")
            lines.append("")
    else:
        lines.append("No duplicates found.")
        lines.append("")
    if lookalikes:
        lines.append(
            "Worth a look, never removed (similar names, or different cards saved from the same page):"
        )
        for a, b in lookalikes:
            lines.append(f"  {a.get('name')}  ~  {b.get('name')}   ({a['_id']} / {b['_id']})")
    return "\n".join(lines)


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Find and remove duplicate credit cards")
    parser.add_argument("--uri", default=os.getenv("MONGODB_URI", "mongodb://localhost:27017"))
    parser.add_argument("--db", default=os.getenv("MONGODB_DB_NAME", "cardsense"))
    parser.add_argument("--apply", action="store_true", help="Delete the duplicate records")
    args = parser.parse_args()

    from pymongo import MongoClient

    with MongoClient(args.uri, serverSelectionTimeoutMS=10_000) as client:
        col = client[args.db][COLLECTION]
        docs = list(col.find({}, FIELDS))
        groups = find_duplicates(docs)
        print(f"Database: {args.uri.split('@')[-1]} / {args.db}\n")
        print(report(docs, groups, find_lookalikes(docs)))
        ids = [d["_id"] for g in groups for d in g["remove"]]
        if not ids:
            return
        if args.apply:
            deleted = col.delete_many({"_id": {"$in": ids}}).deleted_count
            print(f"\nDeleted {deleted} duplicate records.")
        else:
            print(
                f"\nNothing changed. Run again with --apply to delete the {len(ids)} records marked remove."
            )


if __name__ == "__main__":
    main()
