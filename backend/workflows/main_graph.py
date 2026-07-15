"""
BkAI Main LangGraph Workflow.
"""

from __future__ import annotations

import time
from typing import Literal

from langgraph.graph import END, StateGraph

from agents.generator import generate_answer_node
from agents.query_rewriter import query_rewrite_node
from agents.retriever import evaluate_results_node, retrieve_node
from agents.self_reflection import self_reflect_node, should_retry
from agents.state import AgentState
from memory.conversation import get_conversation_memory
from utils.logger import AgentTracer, get_logger

logger = get_logger(__name__)
tracer = AgentTracer("orchestrator")


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("query_rewrite", query_rewrite_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("evaluate_results", evaluate_results_node)
    graph.add_node("generate", generate_answer_node)
    graph.add_node("self_reflect", self_reflect_node)

    graph.set_entry_point("query_rewrite")
    graph.add_edge("query_rewrite", "retrieve")
    graph.add_edge("retrieve", "evaluate_results")

    graph.add_conditional_edges(
        "evaluate_results",
        _route_after_evaluation,
        {
            "sufficient": "generate",
            "need_more": "retrieve",
        },
    )

    graph.add_edge("generate", "self_reflect")

    graph.add_conditional_edges(
        "self_reflect",
        should_retry,
        {"retry": "retrieve", "accept": END},
    )

    return graph


def _route_after_evaluation(state: AgentState) -> Literal["sufficient", "need_more"]:
    decision = state.get("retrieval_decision", "SUFFICIENT")
    if decision == "NEED_MORE":
        return "need_more"
    return "sufficient"


_compiled_graph = None


def get_compiled_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph().compile()
        logger.info("langgraph_compiled")
    return _compiled_graph


async def run_agent_pipeline(
    query: str,
    session_id: str = "default",
    chat_history: list[dict[str, str]] | None = None,
    query_id: str = "",
) -> dict:
    t0 = time.time()
    tracer.start("pipeline", query=query[:80], session_id=session_id)

    memory = get_conversation_memory()
    if chat_history is None:
        chat_history = memory.get_history(session_id)

    initial_state: AgentState = {
        "original_query": query,
        "chat_history": chat_history,
        "session_id": session_id,
        "query_id": query_id,
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
        "iteration_count": 0,
        "step_timings": {},
    }

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
