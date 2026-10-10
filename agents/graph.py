"""
agents/graph.py
─────────────────────────────────────────────────────────────────────────────
LangGraph pipeline for CardSense AI.

Graph topology (Section 5 — Graph Wiring)
──────────────────────────────────────────

  START
    │
    ▼
  pdf_check  ──[pdf_locked]──► wait_password  ──► pdf_check (loop)
    │
    │[parsing]
    ▼
  parse_transactions
    │
    ▼
  question_gen  ──[has pending]──► wait_answer  ──► question_gen (loop)
    │
    │[all answered]
    ▼
  cashback_calc
    │
    ▼
  compare
    │
    ▼
   END

Interrupt behaviour (Section 5)
────────────────────────────────
  interrupt_before=["wait_password", "wait_answer"]

  When the graph hits wait_password or wait_answer, LangGraph pauses and
  serialises state to MongoDB via MongoDBSaver.  The HTTP layer then
  resumes the graph by calling:

    await compiled.ainvoke(
        <updated_state_patch>,
        config={"configurable": {"thread_id": session_id}},
    )

  The patch must inject:
    - For password: cards[locked_card_idx].pdf_passwords[locked_pdf_idx] = password
    - For answer:   cards[current_card_idx].qa_answers[question_id] = answer

Multi-card handling
───────────────────
  The outer API layer calls graph.ainvoke once per card, advancing
  current_card_idx between calls.  compare_node runs once after all cards
  are processed.

Checkpointer
────────────
  Uses MongoDBSaver (langgraph.checkpoint.mongodb) which exposes both
  sync and async methods.  The thread_id = session_id.

  MONGODB_URI and MONGODB_DB_NAME are read from the environment.
─────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import logging
import os
from typing import Any, Literal

from dotenv import load_dotenv
from langgraph.graph import END, START, StateGraph

from agents.cashback_node import cashback_calc_node
from agents.compare_node import compare_node
from agents.parse_node import parse_transactions_node
from agents.pdf_node import pdf_check_node
from agents.question_node import question_gen_node
from agents.state import AnalysisState

load_dotenv()
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Pass-through interrupt nodes
# ─────────────────────────────────────────────────────────────────────────────
# These nodes do nothing themselves — they exist purely as named interrupt
# targets so LangGraph can pause before them and the HTTP layer can inject
# the user's response into state before resuming.


def wait_password_node(state: AnalysisState) -> dict[str, Any]:
    """
    Interrupt target for the password flow.
    When resumed, the HTTP layer will have patched:
      cards[locked_card_idx].pdf_passwords[locked_pdf_idx] = <password>
    The graph then loops back to pdf_check_node.
    """
    # Nothing to do — just a named pause point
    return {}


def wait_answer_node(state: AnalysisState) -> dict[str, Any]:
    """
    Interrupt target for the quiz flow.
    When resumed, the HTTP layer will have patched:
      cards[current_card_idx].qa_answers[question_id] = <bool>
    The graph then loops back to question_gen_node.
    """
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# Conditional edge routers
# ─────────────────────────────────────────────────────────────────────────────


def _route_after_pdf_check(
    state: AnalysisState,
) -> Literal["wait_password", "parse_transactions", "__end__"]:
    """
    After pdf_check_node:
      - pdf_locked  → wait_password (graph pauses; user supplies password)
      - parsing     → parse_transactions
      - error       → END
    """
    status = state.get("status", "")
    if status == "pdf_locked":
        return "wait_password"
    if status == "error":
        return "__end__"
    return "parse_transactions"


def _route_after_question_gen(
    state: AnalysisState,
) -> Literal["wait_answer", "cashback_calc"]:
    """
    After question_gen_node:
      - questioning  → wait_answer (graph pauses; user answers one question)
      - calculating  → cashback_calc (all questions answered)
    """
    status = state.get("status", "")
    if status == "questioning":
        return "wait_answer"
    return "cashback_calc"


# ─────────────────────────────────────────────────────────────────────────────
# Graph factory
# ─────────────────────────────────────────────────────────────────────────────


def build_graph(checkpointer=None) -> Any:
    """
    Build and compile the CardSense analysis StateGraph.

    Parameters
    ----------
    checkpointer : optional LangGraph checkpointer
        Pass a MongoDBSaver (or any BaseCheckpointSaver) to enable
        cross-HTTP-request state persistence.  Pass None for testing.

    Returns
    -------
    CompiledGraph  (langgraph compiled graph object)
    """
    graph = StateGraph(AnalysisState)

    # ── Register nodes ────────────────────────────────────────────────
    graph.add_node("pdf_check", pdf_check_node)
    graph.add_node("wait_password", wait_password_node)
    graph.add_node("parse_transactions", parse_transactions_node)
    graph.add_node("question_gen", question_gen_node)
    graph.add_node("wait_answer", wait_answer_node)
    graph.add_node("cashback_calc", cashback_calc_node)
    graph.add_node("compare", compare_node)

    # ── Entry point ───────────────────────────────────────────────────
    graph.add_edge(START, "pdf_check")

    # ── pdf_check → conditional ───────────────────────────────────────
    graph.add_conditional_edges(
        "pdf_check",
        _route_after_pdf_check,
        {
            "wait_password": "wait_password",
            "parse_transactions": "parse_transactions",
            "__end__": END,
        },
    )

    # ── wait_password → pdf_check (resume after password supplied) ────
    graph.add_edge("wait_password", "pdf_check")

    # ── parse_transactions → question_gen ─────────────────────────────
    graph.add_edge("parse_transactions", "question_gen")

    # ── question_gen → conditional ────────────────────────────────────
    graph.add_conditional_edges(
        "question_gen",
        _route_after_question_gen,
        {
            "wait_answer": "wait_answer",
            "cashback_calc": "cashback_calc",
        },
    )

    # ── wait_answer → question_gen (re-evaluate after each answer) ────
    graph.add_edge("wait_answer", "question_gen")

    # ── cashback_calc → compare → END ─────────────────────────────────
    graph.add_edge("cashback_calc", "compare")
    graph.add_edge("compare", END)

    # ── Compile with checkpointer and interrupt points ────────────────
    compiled = graph.compile(
        checkpointer=checkpointer,
        interrupt_before=["wait_password", "wait_answer"],
    )

    logger.info("CardSense graph compiled (checkpointer=%s)", type(checkpointer).__name__)
    return compiled


# ─────────────────────────────────────────────────────────────────────────────
# Checkpointer factory
# ─────────────────────────────────────────────────────────────────────────────


def create_checkpointer() -> Any:
    """
    Instantiate a MongoDBSaver for use as the LangGraph checkpointer.

    The checkpointer persists graph state between HTTP calls using
    thread_id = session_id.

    Returns None if MONGODB_URI is not set (test/dev mode).
    """
    uri = os.getenv("MONGODB_URI", "")
    db_name = os.getenv("MONGODB_DB_NAME", "cardsense")

    if not uri:
        logger.warning("MONGODB_URI not set — running without checkpointer (stateless)")
        return None

    try:
        from langgraph.checkpoint.mongodb import MongoDBSaver
        from pymongo import MongoClient

        # MongoDBSaver.from_conn_string is a context manager, not a saver, so
        # build the saver around a long-lived client instead
        checkpointer = MongoDBSaver(
            MongoClient(uri, serverSelectionTimeoutMS=10_000),
            db_name=db_name,
            checkpoint_collection_name="lg_checkpoints",
            writes_collection_name="lg_checkpoint_writes",
        )
        logger.info("MongoDBSaver checkpointer created (db=%s)", db_name)
        return checkpointer
    except Exception as exc:
        logger.error("Failed to create MongoDBSaver: %s — running stateless", exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Module-level compiled graph (lazy singleton)
# ─────────────────────────────────────────────────────────────────────────────
# The FastAPI app imports `get_compiled_graph()` which creates the compiled
# graph once on first call and reuses it for all subsequent requests.

_compiled_graph = None


def get_compiled_graph(force_new: bool = False) -> Any:
    """
    Return the module-level compiled graph singleton.
    Creates it on first call using MongoDBSaver if MONGODB_URI is configured.
    """
    global _compiled_graph
    if _compiled_graph is None or force_new:
        checkpointer = create_checkpointer()
        _compiled_graph = build_graph(checkpointer=checkpointer)
    return _compiled_graph


# ─────────────────────────────────────────────────────────────────────────────
# Graph invocation helpers (used by API routes)
# ─────────────────────────────────────────────────────────────────────────────


def _make_thread_config(session_id: str) -> dict:
    """Return the LangGraph config dict for a given session."""
    return {"configurable": {"thread_id": session_id}}


async def ainvoke_graph(
    state_or_patch: dict,
    session_id: str,
    graph=None,
) -> AnalysisState:
    """
    Async wrapper for graph invocation.

    On first call (new session): pass the full initial AnalysisState.
    On resume (password / answer supplied): pass a state patch dict.

    Parameters
    ----------
    state_or_patch : dict
        Full AnalysisState for new sessions, or partial patch for resumes.
    session_id : str
        Used as the LangGraph thread_id for checkpointing.
    graph : optional compiled graph
        Defaults to the module singleton.

    Returns
    -------
    AnalysisState — the final state after the graph pauses or completes.
    """
    if graph is None:
        graph = get_compiled_graph()

    config = _make_thread_config(session_id)

    try:
        result = await graph.ainvoke(state_or_patch, config=config)
        return result
    except Exception as exc:
        logger.error("Graph invocation error (session=%s): %s", session_id, exc)
        raise


async def aget_graph_state(session_id: str, graph=None) -> AnalysisState | None:
    """
    Retrieve the current checkpointed state for a session without running the graph.
    Returns None if no checkpoint exists.
    """
    if graph is None:
        graph = get_compiled_graph()

    config = _make_thread_config(session_id)

    try:
        snapshot = await graph.aget_state(config)
        return snapshot.values if snapshot else None
    except Exception as exc:
        logger.error("Failed to get graph state (session=%s): %s", session_id, exc)
        return None


async def aupdate_graph_state(
    patch: dict,
    session_id: str,
    graph=None,
) -> None:
    """
    Merge a patch dict into the current checkpointed state without running nodes.
    Used by the API to inject password or answer into state before resuming.
    """
    if graph is None:
        graph = get_compiled_graph()

    config = _make_thread_config(session_id)

    try:
        await graph.aupdate_state(config, patch)
    except Exception as exc:
        logger.error("Failed to update graph state (session=%s): %s", session_id, exc)
        raise
