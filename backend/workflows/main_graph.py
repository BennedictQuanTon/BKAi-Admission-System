"""
BKAi Main LangGraph Workflow.

Defines the complete agent pipeline as a LangGraph state machine:

    CheckCache → QueryRewrite → Retrieve → Evaluate
        ↓ (sufficient)        ↓ (need_more → loop back)
    Generate → SelfReflect → Return
        ↑ (low confidence)  ↓ (accept)
        └───────────────── Done
"""

from __future__ import annotations

import time
from typing import Literal

from langgraph.graph import StateGraph, END

from agents.state import AgentState
from agents.query_rewriter import query_rewrite_node
from agents.retriever import retrieve_node, evaluate_results_node
from agents.generator import generate_answer_node
from agents.self_reflection import self_reflect_node, should_retry
from memory.conversation import get_conversation_memory
from utils.logger import get_logger, AgentTracer

logger = get_logger(__name__)
tracer = AgentTracer("orchestrator")


# ──────────────────────────────────────────────
# Graph Construction
# ──────────────────────────────────────────────
def build_graph() -> StateGraph:
    """
    Build the LangGraph state machine for the Agentic RAG pipeline.

    Graph structure:
        query_rewrite → retrieve → evaluate_results
            → (SUFFICIENT) → generate → self_reflect
                → (accept) → END
                → (retry) → retrieve (re-retrieve)
            → (NEED_MORE) → retrieve (multi-hop loop)
            → (NO_DATA) → generate (with "no data" context)
    """
    graph = StateGraph(AgentState)

    # ── Add nodes ──
    graph.add_node("query_rewrite", query_rewrite_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("evaluate_results", evaluate_results_node)
    graph.add_node("generate", generate_answer_node)
    graph.add_node("self_reflect", self_reflect_node)

    # ── Set entry point ──
    graph.set_entry_point("query_rewrite")

    # ── Add edges ──
    # query_rewrite → retrieve
    graph.add_edge("query_rewrite", "retrieve")

    # retrieve → evaluate_results
    graph.add_edge("retrieve", "evaluate_results")

    # evaluate_results → conditional routing
    graph.add_conditional_edges(
        "evaluate_results",
        _route_after_evaluation,
        {
            "sufficient": "generate",
            "need_more": "retrieve",
            "no_data": "generate",
        },
    )

    # generate → self_reflect
    graph.add_edge("generate", "self_reflect")

    # self_reflect → conditional routing
    graph.add_conditional_edges(
        "self_reflect",
        should_retry,
        {
            "retry": "retrieve",
            "accept": END,
        },
    )

    return graph


def _route_after_evaluation(state: AgentState) -> Literal["sufficient", "need_more", "no_data"]:
    """Route based on retrieval evaluation decision."""
    decision = state.get("retrieval_decision", "SUFFICIENT")

    if decision == "NEED_MORE":
        return "need_more"
    elif decision == "NO_DATA":
        return "no_data"
    return "sufficient"


# ──────────────────────────────────────────────
# Compiled Graph (singleton)
# ──────────────────────────────────────────────
_compiled_graph = None


def get_compiled_graph():
    """Get or build the compiled LangGraph workflow."""
    global _compiled_graph
    if _compiled_graph is None:
        graph = build_graph()
        _compiled_graph = graph.compile()
        logger.info("langgraph_compiled")
    return _compiled_graph


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────
async def run_agent_pipeline(
    query: str,
    session_id: str = "default",
    chat_history: list[dict[str, str]] | None = None,
) -> dict:
    """
    Run the complete agent pipeline for a user query.

    This is the main entry point called by the API layer.

    Args:
        query: User's question.
        session_id: Session identifier for conversation memory.
        chat_history: Optional previous conversation turns.

    Returns:
        Dict with 'answer', 'confidence', 'timings', and metadata.
    """
    t0 = time.time()
    tracer.start("pipeline", query=query[:80], session_id=session_id)

    # Get conversation history
    memory = get_conversation_memory()
    if chat_history is None:
        chat_history = memory.get_history(session_id)

    # Build initial state
    initial_state: AgentState = {
        "original_query": query,
        "chat_history": chat_history,
        "session_id": session_id,
        "rewritten_queries": [],
        "hyde_document": "",
        "search_results": [],
        "reranked_results": [],
        "retrieval_context": "",
        "retrieval_hops": 0,
        "retrieval_decision": "",
        "generated_answer": "",
        "answer_confidence": 0.0,
        "answer_issues": [],
        "current_step": "start",
        "error": None,
        "should_web_search": False,
        "iteration_count": 0,
        "step_timings": {},
    }

    # Run the graph
    graph = get_compiled_graph()

    try:
        final_state = await graph.ainvoke(initial_state)
    except Exception as e:
        logger.error("pipeline_error", error=str(e))
        final_state = {
            **initial_state,
            "generated_answer": (
                "Xin lỗi, tôi gặp sự cố khi xử lý câu hỏi. "
                "Vui lòng thử lại."
            ),
            "answer_confidence": 0.0,
            "error": str(e),
        }

    # Update conversation memory
    memory.add_turn(session_id, "user", query)
    memory.add_turn(session_id, "assistant", final_state.get("generated_answer", ""))

    elapsed = time.time() - t0
    tracer.end("pipeline", elapsed=round(elapsed, 2))

    return {
        "answer": final_state.get("generated_answer", ""),
        "confidence": final_state.get("answer_confidence", 0.0),
        "issues": final_state.get("answer_issues", []),
        "rewritten_queries": final_state.get("rewritten_queries", []),
        "retrieval_decision": final_state.get("retrieval_decision", ""),
        "timings": {
            **final_state.get("step_timings", {}),
            "total": round(elapsed, 3),
        },
        "retrieval_hops": final_state.get("retrieval_hops", 0),
        "sources": [
            r.get("metadata", {}).get("source_file", "unknown")
            for r in final_state.get("reranked_results", [])[:5]
        ],
        "session_id": session_id,
    }
