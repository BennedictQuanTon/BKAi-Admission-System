"""
BkAI Multi-hop Retrieval Agent — hybrid search, HyDE, reranking.
"""

from __future__ import annotations

import re
import time

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agents.state import AgentState, format_context, serialize_results
from config.prompts import MULTI_HOP_RETRIEVER_PROMPT
from config.settings import get_settings
from services.llm_factory import acquire_rpm_slot, get_fast_llm
from tools.hybrid_search import hybrid_search
from tools.reranker import rerank
from utils.logger import AgentTracer

from api.dashboard_manager import stream_progress

tracer = AgentTracer("retriever")
MAX_HOPS = 3


class EvaluateOutput(BaseModel):
    decision: str = Field(description="SUFFICIENT | NEED_MORE | NO_DATA")
    follow_up_query: str = ""


async def retrieve_node(state: AgentState) -> dict:
    t0 = time.time()
    settings = get_settings()
    queries = list(state.get("rewritten_queries", [state["original_query"]]))
    hyde_doc = state.get("hyde_document", "")
    session_id = state.get("session_id", "")
    query_id = state.get("query_id", "")

    stream_progress(
        session_id=session_id,
        query_id=query_id,
        step="retrieve",
        status="running",
        message=f"Querying vector database with {len(queries)} query variations (RAG)...",
    )

    if hyde_doc and len(hyde_doc) > 50:
        queries.append(hyde_doc[:500])

    tracer.start("retrieve", queries=len(queries))

    all_results = []
    seen_contents: set[str] = set()

    for query in queries:
        results = hybrid_search(query, top_k=settings.search.retrieval_top_k)
        for r in results:
            key = r.content[:150]
            if key not in seen_contents:
                seen_contents.add(key)
                all_results.append(r)

    original = state["original_query"]
    reranked = rerank(original, all_results, top_k=settings.search.rerank_top_k)

    elapsed = time.time() - t0
    tracer.end("retrieve", results=len(reranked), elapsed=round(elapsed, 2))

    serialized = serialize_results(reranked)
    context = format_context(serialized, max_chars=4000)

    stream_progress(
        session_id=session_id,
        query_id=query_id,
        step="retrieve",
        status="done",
        message=f"Retrieval completed in {elapsed:.2f}s. Found {len(reranked)} relevant document chunks.",
        elapsed=round(elapsed, 3),
    )

    return {
        "search_results": serialize_results(all_results),
        "reranked_results": serialized,
        "retrieval_context": context,
        "retrieval_hops": state.get("retrieval_hops", 0) + 1,
        "current_step": "retrieve",
        "step_timings": {
            **state.get("step_timings", {}),
            "retrieve": round(elapsed, 3),
        },
    }


async def evaluate_results_node(state: AgentState) -> dict:
    t0 = time.time()
    session_id = state.get("session_id", "")
    query_id = state.get("query_id", "")

    stream_progress(
        session_id=session_id,
        query_id=query_id,
        step="evaluate_results",
        status="running",
        message="Evaluating completeness and relevance of retrieved documents...",
    )
    tracer.start("evaluate_results")

    results = state.get("reranked_results", [])
    hops = state.get("retrieval_hops", 1)
    original = state["original_query"]

    if not results:
        decision = "SUFFICIENT"
    elif hops >= MAX_HOPS:
        decision = "SUFFICIENT"
    elif len(results) >= 3 and results[0].get("score", 0) > 0.01:
        decision = "SUFFICIENT"
    else:
        decision = await _llm_evaluate(original, results)
        if decision == "NO_DATA":
            decision = "SUFFICIENT"

    elapsed = time.time() - t0
    tracer.end("evaluate_results", decision=decision, elapsed=round(elapsed, 2))

    stream_progress(
        session_id=session_id,
        query_id=query_id,
        step="evaluate_results",
        status="done",
        message=f"Evaluation completed in {elapsed:.2f}s. Decision: {decision}.",
        elapsed=round(elapsed, 3),
    )

    return {
        "retrieval_decision": decision,
        "should_web_search": False,
        "current_step": "evaluate_results",
        "step_timings": {
            **state.get("step_timings", {}),
            "evaluate_results": round(elapsed, 3),
        },
    }


async def _llm_evaluate(query: str, results: list[dict]) -> str:
    snippets = [r.get("content", "")[:200] for r in results[:5]]
    context_summary = "\n---\n".join(snippets)

    try:
        await acquire_rpm_slot("fast")
        llm = get_fast_llm().with_structured_output(EvaluateOutput)
        result: EvaluateOutput = await llm.ainvoke([
            SystemMessage(content=MULTI_HOP_RETRIEVER_PROMPT),
            HumanMessage(content=(
                f"Câu hỏi: {query}\n\n"
                f"Kết quả tìm kiếm ({len(results)} kết quả):\n{context_summary}"
            )),
        ])
        return result.decision if result.decision in {"SUFFICIENT", "NEED_MORE", "NO_DATA"} else "SUFFICIENT"
    except Exception:
        return "SUFFICIENT"


def query_has_numeric_facts(query: str) -> bool:
    """Detect questions likely needing factual verification."""
    patterns = [
        r"điểm\s*chuẩn",
        r"học\s*phí",
        r"chỉ\s*tiêu",
        r"mã\s*ngành",
        r"\b20[0-9]{2}\b",
        r"\b\d{2,3}[,.]?\d*\b",
    ]
    text = query.lower()
    return any(re.search(p, text) for p in patterns)
