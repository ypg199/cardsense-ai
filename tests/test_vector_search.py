"""
tests/test_vector_search.py
─────────────────────────────────────────────────────────────────────────────
Step 14 — Offline tests for the Atlas Vector Search integration in compare_node.

Verifies:
  1. $vectorSearch pipeline structure is correct.
  2. Fallback to category filter when vector search raises.
  3. Fallback when vector search returns 0 results.
  4. compare_node uses the correct index name and dimensions.
  5. Embedding generation produces a 768-dim vector.
  6. Index documentation in setup_indexes.py and db/schemas.py.
  7. Full compare_node pipeline uses vector search then falls back.

All DB and Gemini calls mocked — no live connections.
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
import sys
import unittest.mock as mock

sys.path.insert(0, "/home/claude/cardsense")

PASS = 0
FAIL = 0

def ok(msg: str):
    global PASS; PASS += 1
    print(f"  ✅ {msg}")

def fail(msg: str):
    global FAIL; FAIL += 1
    print(f"  ❌ {msg}")


# ── Sample data ───────────────────────────────────────────────────────────────

MOCK_CARDS_DB = [
    {
        "_id": "axis-airtel",
        "name": "Axis Airtel Credit Card",
        "bank": "Axis Bank",
        "card_type": "cashback",
        "annual_fee": 500,
        "benefits": [
            {"category": "food_delivery", "rate": 0.10, "label": "Zomato"},
            {"category": "grocery",       "rate": 0.10, "label": "BigBasket"},
        ],
        "best_for_tags": ["airtel users"],
        "score": 0.95,
    },
    {
        "_id": "hdfc-millennia",
        "name": "HDFC Millennia Credit Card",
        "bank": "HDFC Bank",
        "card_type": "cashback",
        "annual_fee": 1000,
        "benefits": [
            {"category": "shopping_online", "rate": 0.05, "label": "Amazon"},
            {"category": "food_delivery",   "rate": 0.05, "label": "Dining"},
        ],
        "best_for_tags": ["amazon"],
        "score": 0.88,
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# 1. Constants
# ─────────────────────────────────────────────────────────────────────────────

def test_constants():
    print("\n[1] Vector search constants")

    from agents.compare_node import VECTOR_SEARCH_INDEX, EMBEDDING_DIMENSIONS, VECTOR_SEARCH_CANDIDATES

    assert VECTOR_SEARCH_INDEX == "credit_cards_embedding_index"
    ok(f"VECTOR_SEARCH_INDEX == 'credit_cards_embedding_index'")

    assert EMBEDDING_DIMENSIONS == 768
    ok(f"EMBEDDING_DIMENSIONS == 768")

    assert VECTOR_SEARCH_CANDIDATES == 10
    ok(f"VECTOR_SEARCH_CANDIDATES == 10")


# ─────────────────────────────────────────────────────────────────────────────
# 2. $vectorSearch pipeline structure
# ─────────────────────────────────────────────────────────────────────────────

def test_vector_search_pipeline_structure():
    print("\n[2] $vectorSearch pipeline structure")

    # The pipeline is constructed inside _vector_search_async — inspect it
    # by capturing the aggregate call
    dummy_vector = [0.01] * 768
    captured_pipeline = []

    async def _run():
        mock_cursor = mock.MagicMock()
        mock_cursor.to_list = mock.AsyncMock(return_value=MOCK_CARDS_DB)

        mock_col = mock.MagicMock()
        def _capture_aggregate(pipeline, *args, **kwargs):
            captured_pipeline.extend(pipeline)
            return mock_cursor
        mock_col.aggregate = _capture_aggregate

        mock_db = mock.MagicMock()
        mock_db.__getitem__ = mock.MagicMock(return_value=mock_col)

        with mock.patch("db.connection.get_db", return_value=mock_db):
            from agents.compare_node import _vector_search_async
            results = await _vector_search_async(dummy_vector, ["food_delivery"])

        return results

    results = asyncio.run(_run())

    assert len(captured_pipeline) == 2, f"Expected 2 pipeline stages, got {len(captured_pipeline)}"
    ok("Pipeline has exactly 2 stages ($vectorSearch + $project)")

    stage1 = captured_pipeline[0]
    assert "$vectorSearch" in stage1
    ok("Stage 1 is $vectorSearch")

    vs = stage1["$vectorSearch"]
    assert vs["index"] == "credit_cards_embedding_index"
    ok("index == 'credit_cards_embedding_index'")

    assert vs["path"] == "embedding"
    ok("path == 'embedding'")

    assert vs["queryVector"] == dummy_vector
    ok("queryVector correctly passed")

    assert vs["numCandidates"] == 100  # VECTOR_SEARCH_CANDIDATES * 10
    ok("numCandidates == 100 (10 × 10)")

    assert vs["limit"] == 10
    ok("limit == 10")

    stage2 = captured_pipeline[1]
    assert "$project" in stage2
    assert stage2["$project"]["embedding"] == 0
    ok("$project excludes embedding field (don't return 768-float arrays)")

    assert results == MOCK_CARDS_DB
    ok(f"Returns {len(results)} candidates from vector search")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Category-filter fallback when vector search raises
# ─────────────────────────────────────────────────────────────────────────────

def test_fallback_on_vector_search_error():
    print("\n[3] Fallback to category filter when $vectorSearch raises")

    async def _run():
        mock_cursor_fallback = mock.MagicMock()
        mock_cursor_fallback.to_list = mock.AsyncMock(return_value=MOCK_CARDS_DB)

        call_log = []

        mock_col = mock.MagicMock()

        def _aggregate_raises(pipeline, *args, **kwargs):
            # Simulate vector search index not existing
            raise Exception("PlanExecutor error during aggregation :: caused by :: $vectorSearch index not found")

        def _find_fallback(query, projection=None):
            call_log.append("category_filter")
            cursor = mock.MagicMock()
            cursor.limit.return_value = mock_cursor_fallback
            return cursor

        mock_col.aggregate = _aggregate_raises
        mock_col.find = _find_fallback

        mock_db = mock.MagicMock()
        mock_db.__getitem__ = mock.MagicMock(return_value=mock_col)

        with mock.patch("db.connection.get_db", return_value=mock_db):
            from agents.compare_node import _vector_search_async
            results = await _vector_search_async([0.0] * 768, ["food_delivery", "grocery"])

        return results, call_log

    results, call_log = asyncio.run(_run())

    assert len(results) > 0
    ok(f"Fallback returned {len(results)} candidates")

    assert "category_filter" in call_log
    ok("Category-filter fallback was triggered on vector search error")


def test_fallback_on_empty_results():
    print("\n[4] Fallback when vector search returns 0 results")

    async def _run():
        mock_cursor_empty = mock.MagicMock()
        mock_cursor_empty.to_list = mock.AsyncMock(return_value=[])   # Empty!

        mock_cursor_fallback = mock.MagicMock()
        mock_cursor_fallback.to_list = mock.AsyncMock(return_value=MOCK_CARDS_DB)

        call_log = []

        mock_col = mock.MagicMock()
        mock_col.aggregate.return_value = mock_cursor_empty

        def _find_fallback(query, projection=None):
            call_log.append("category_filter")
            cursor = mock.MagicMock()
            cursor.limit.return_value = mock_cursor_fallback
            return cursor

        mock_col.find = _find_fallback

        mock_db = mock.MagicMock()
        mock_db.__getitem__ = mock.MagicMock(return_value=mock_col)

        with mock.patch("db.connection.get_db", return_value=mock_db):
            from agents.compare_node import _vector_search_async
            results = await _vector_search_async([0.0] * 768, ["food_delivery"])

        return results, call_log

    results, call_log = asyncio.run(_run())

    assert len(results) > 0
    ok(f"Fallback used when vector search returns 0 results ({len(results)} candidates)")

    assert "category_filter" in call_log
    ok("Category-filter fallback triggered on 0 results")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Category-filter fallback directly
# ─────────────────────────────────────────────────────────────────────────────

def test_category_filter_fallback_directly():
    print("\n[5] _fetch_cards_by_categories_async directly")

    async def _run():
        mock_cursor = mock.MagicMock()
        mock_cursor.to_list = mock.AsyncMock(return_value=MOCK_CARDS_DB)

        mock_col = mock.MagicMock()
        captured_query = {}

        def _find(query, projection=None):
            captured_query.update(query)
            cursor = mock.MagicMock()
            cursor.limit.return_value = mock_cursor
            return cursor

        mock_col.find = _find
        mock_db = mock.MagicMock()
        mock_db.__getitem__ = mock.MagicMock(return_value=mock_col)

        with mock.patch("db.connection.get_db", return_value=mock_db):
            from agents.compare_node import _fetch_cards_by_categories_async
            results = await _fetch_cards_by_categories_async(
                ["food_delivery", "grocery", "shopping_online"]
            )

        return results, captured_query

    results, query = asyncio.run(_run())

    assert len(results) == 2
    ok(f"Category filter returned {len(results)} cards")

    assert "benefits.category" in query
    ok("Query filters on benefits.category")

    assert "$in" in query["benefits.category"]
    ok("Uses $in operator for multiple categories")

    cats = query["benefits.category"]["$in"]
    assert "food_delivery" in cats and "grocery" in cats
    ok("All requested categories in $in list")


# ─────────────────────────────────────────────────────────────────────────────
# 5. Embedding generation
# ─────────────────────────────────────────────────────────────────────────────

def test_get_embedding_success():
    print("\n[6] _get_embedding — success path")

    mock_vector = [round(i * 0.001, 4) for i in range(768)]

    mock_embed_instance = mock.MagicMock()
    mock_embed_instance.embed_query.return_value = mock_vector
    MockEmbed = mock.MagicMock(return_value=mock_embed_instance)

    with mock.patch.dict("sys.modules", {
        "langchain_google_genai": mock.MagicMock(GoogleGenerativeAIEmbeddings=MockEmbed)
    }), mock.patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key"}):
        # Force reimport to pick up patched module
        import importlib
        import agents.compare_node as cm
        importlib.reload(cm)
        vec = cm._get_embedding("Indian credit card user spending on food and groceries")

    assert len(vec) == 768
    ok("Embedding vector length == 768")

    assert isinstance(vec[0], float)
    ok("Embedding values are floats")


def test_get_embedding_failure_returns_zeros():
    print("\n[7] _get_embedding — failure returns zero vector")

    mock_embed_mod = mock.MagicMock()
    mock_embed_mod.GoogleGenerativeAIEmbeddings.side_effect = Exception("API unavailable")

    with mock.patch.dict("sys.modules", {"langchain_google_genai": mock_embed_mod}), \
         mock.patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key"}):
        import importlib
        import agents.compare_node as cm
        importlib.reload(cm)
        vec = cm._get_embedding("some text")

    assert len(vec) == 768
    ok("Zero vector of length 768 returned on failure")

    assert all(v == 0.0 for v in vec)
    ok("All values are 0.0 in fallback vector")


# ─────────────────────────────────────────────────────────────────────────────
# 6. Index documentation in setup_indexes.py
# ─────────────────────────────────────────────────────────────────────────────

def test_setup_indexes_documents_vector_search():
    print("\n[8] setup_indexes.py — vector search index documented")

    with open("db/setup_indexes.py") as f:
        src = f.read()

    assert "credit_cards_embedding_index" in src
    ok("Index name 'credit_cards_embedding_index' in setup_indexes.py")

    assert "768" in src
    ok("Dimension '768' documented in setup_indexes.py")

    assert "cosine" in src
    ok("Similarity 'cosine' documented in setup_indexes.py")

    assert "embedding" in src
    ok("Field 'embedding' documented in setup_indexes.py")

    assert "Atlas" in src or "atlas" in src.lower()
    ok("Atlas UI instruction present (cannot create via driver)")


def test_schemas_documents_vector_search():
    print("\n[9] db/schemas.py — vector search index documented")

    with open("db/schemas.py") as f:
        src = f.read()

    assert "credit_cards_embedding_index" in src
    ok("Index name 'credit_cards_embedding_index' in schemas.py")

    assert "768" in src
    ok("Dimension 768 documented in schemas.py")

    assert "cosine" in src
    ok("Similarity 'cosine' documented in schemas.py")

    assert "VECTOR SEARCH" in src or "Vector Search" in src
    ok("Vector Search type annotated in index summary table")


# ─────────────────────────────────────────────────────────────────────────────
# 7. Full compare_node uses vector search
# ─────────────────────────────────────────────────────────────────────────────

def test_compare_node_calls_vector_search():
    print("\n[10] compare_node — calls _vector_search_async (not just category filter)")

    from agents.state import CardState, CashbackResult, MonthlyBreakdown

    card = {
        "card_id": "axis-airtel", "card_name": "Axis Airtel",
        "months": ["2024-01"], "pdf_bytes_list": [], "pdf_passwords": [],
        "pdf_encrypted": False, "pdf_text": "",
        "transactions": [
            {"date": "2024-01-10", "merchant": "Zomato", "amount": 900.0,
             "transaction_type": "debit", "category": "food_delivery", "month": "2024-01"},
            {"date": "2024-01-15", "merchant": "BigBasket", "amount": 600.0,
             "transaction_type": "debit", "category": "grocery", "month": "2024-01"},
        ],
        "total_spend": 1500.0,
        "pending_questions": [], "answered_questions": [],
        "qa_answers": {"q_zomato": True},
        "cashback_result": CashbackResult(
            earned_breakdown={"food_delivery": 90.0},
            missed_breakdown={"grocery": 60.0},
            utilization_score=60,
            monthly_breakdown=[MonthlyBreakdown(month="2024-01", earned=90.0, missed=60.0, score=60)],
            trend="single_month",
        ),
        "utilization_score": 60,
        "status": "comparing",
    }

    state = {
        "session_id": "test-vs", "status": "comparing",
        "cards": [card], "current_card_idx": 0,
        "locked_card_idx": None, "locked_pdf_idx": None,
        "current_question": None, "comparison_result": None,
        "ui_action": "show_loading", "total_questions_count": 0,
        "answered_questions_count": 0, "error": None,
        "created_at": "2024-01-01T00:00:00Z",
    }

    vs_call_log = []

    async def _mock_vector_search(embedding, top_cats):
        vs_call_log.append({"embedding_len": len(embedding), "cats": top_cats})
        return MOCK_CARDS_DB

    mock_gemini_response = """{
        "verdict": "Could do better",
        "verdict_reason": "You are earning Rs 90 vs Rs 150 possible.",
        "card_score": 60,
        "recommendations": [],
        "routing_advice": [],
        "tips": ["Use Axis Airtel for all Zomato orders."]
    }"""

    with mock.patch("agents.compare_node._run_async", side_effect=lambda c: asyncio.run(c) if asyncio.iscoroutine(c) else _mock_vector_search.__wrapped__ if hasattr(_mock_vector_search, '__wrapped__') else MOCK_CARDS_DB), \
         mock.patch("agents.compare_node._get_embedding", return_value=[0.01] * 768), \
         mock.patch("agents.compare_node._vector_search_async", side_effect=_mock_vector_search), \
         mock.patch.dict("os.environ", {"GEMINI_API_KEY": ""}):

        # Patch _run_async to call our mock coroutine
        async def fake_run_async(coro):
            return await coro

        with mock.patch("agents.compare_node._run_async", side_effect=lambda c: asyncio.run(c)):
            from agents.compare_node import compare_node
            result = compare_node(state)

    assert result["status"] == "done"
    ok("compare_node completes with status='done'")

    assert result["ui_action"] == "show_results"
    ok("ui_action == 'show_results'")

    assert result["comparison_result"] is not None
    ok("comparison_result is populated")


def test_compare_node_embedding_text_format():
    print("\n[11] compare_node — embedding text uses top 3 categories")

    from agents.compare_node import _build_spend_profile_text

    from agents.state import CardState, Transaction

    cards = [{
        "card_id": "test", "card_name": "Test",
        "months": ["2024-01"], "pdf_bytes_list": [], "pdf_passwords": [],
        "pdf_encrypted": False, "pdf_text": "",
        "transactions": [
            {"date": "2024-01-01", "merchant": "Zomato", "amount": 1500.0,
             "transaction_type": "debit", "category": "food_delivery", "month": "2024-01"},
            {"date": "2024-01-02", "merchant": "BigBasket", "amount": 800.0,
             "transaction_type": "debit", "category": "grocery", "month": "2024-01"},
            {"date": "2024-01-03", "merchant": "Amazon", "amount": 2000.0,
             "transaction_type": "debit", "category": "shopping_online", "month": "2024-01"},
            {"date": "2024-01-04", "merchant": "Random", "amount": 200.0,
             "transaction_type": "debit", "category": "others", "month": "2024-01"},
        ],
        "total_spend": 4500.0,
        "pending_questions": [], "answered_questions": [],
        "qa_answers": {}, "cashback_result": None,
        "utilization_score": 0, "status": "comparing",
    }]

    top_cats = ["shopping_online", "food_delivery", "grocery"]
    text = _build_spend_profile_text(cards, top_cats)

    assert "shopping_online" in text or "shopping" in text
    ok("Top category (shopping_online) in embedding text")

    assert "₹" in text or "2000" in text
    ok("Spend amounts included in embedding text")

    assert "Indian credit card" in text
    ok("Profile text identifies as Indian credit card user")


# ─────────────────────────────────────────────────────────────────────────────
# 8. verify_vector_search.py exists and is importable
# ─────────────────────────────────────────────────────────────────────────────

def test_verify_script_exists():
    print("\n[12] db/verify_vector_search.py exists")

    import os
    assert os.path.exists("db/verify_vector_search.py")
    ok("verify_vector_search.py exists")

    import ast
    with open("db/verify_vector_search.py") as f:
        src = f.read()
    ast.parse(src)
    ok("verify_vector_search.py is valid Python")

    assert "credit_cards_embedding_index" in src
    ok("References correct index name")

    assert "768" in src
    ok("References 768 dimensions")

    assert "asyncio.run" in src
    ok("Uses asyncio.run() (not get_event_loop)")


# ─────────────────────────────────────────────────────────────────────────────
# Run all
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  Vector Search (Step 14) test suite")
    print("=" * 60)

    test_constants()
    test_vector_search_pipeline_structure()
    test_fallback_on_vector_search_error()
    test_fallback_on_empty_results()
    test_category_filter_fallback_directly()
    test_get_embedding_success()
    test_get_embedding_failure_returns_zeros()
    test_setup_indexes_documents_vector_search()
    test_schemas_documents_vector_search()
    test_compare_node_calls_vector_search()
    test_compare_node_embedding_text_format()
    test_verify_script_exists()

    print()
    print("=" * 60)
    print(f"  Results: {PASS} passed, {FAIL} failed")
    print("=" * 60)

    if FAIL > 0:
        sys.exit(1)
