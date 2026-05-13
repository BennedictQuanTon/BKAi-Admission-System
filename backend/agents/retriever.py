"""
BKAi Multi-hop Retrieval Agent.

Performs iterative retrieval with result evaluation.
Decides whether results are sufficient or need more searching.
"""

from __future__ import annotations

import json
import time

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_ollama import ChatOllama

from agents.state import AgentState, serialize_results, format_context
from config.settings import get_settings
from config.prompts import MULTI_HOP_RETRIEVER_PROMPT
from tools.hybrid_search import hybrid_search
from tools.reranker import rerank
from utils.logger import AgentTracer

tracer = AgentTracer("retriever")

MAX_HOPS = 3


def retrieve_node(state: AgentState) -> dict:
    """
    LangGraph node: Perform hybrid search + reranking.

    Searches using all rewritten queries and merges results.
    """
    t0 = time.time()
    queries = state.get("rewritten_queries", [state["original_query"]])
    tracer.start("retrieve", queries=len(queries))

    all_results = []
    seen_contents: set[str] = set()

    for query in queries:
        results = hybrid_search(query, top_k=15)
        for r in results:
            key = r.content[:150]
            if key not in seen_contents:
                seen_contents.add(key)
                all_results.append(r)

    # Rerank all merged results against original query
    original = state["original_query"]
    reranked = rerank(original, all_results, top_k=8)

    elapsed = time.time() - t0
    tracer.end("retrieve", results=len(reranked), elapsed=round(elapsed, 2))

    serialized = serialize_results(reranked)
    context = format_context(serialized, max_chars=4000)

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


def evaluate_results_node(state: AgentState) -> dict:
    """
    LangGraph node: Evaluate if retrieval results are sufficient.

    Uses the fast model to make a quick SUFFICIENT/NEED_MORE/NO_DATA decision.
    """
    t0 = time.time()
    tracer.start("evaluate_results")

    results = state.get("reranked_results", [])
    hops = state.get("retrieval_hops", 1)
    original = state["original_query"]

    # Quick heuristics first
    if not results:
        decision = "NO_DATA"
    elif hops >= MAX_HOPS:
        decision = "SUFFICIENT"  # Stop after max hops
    elif len(results) >= 3 and results[0].get("score", 0) > 5.0:
        decision = "SUFFICIENT"  # High-confidence results
    else:
        # Use LLM for nuanced evaluation
        decision = _llm_evaluate(original, results)

    elapsed = time.time() - t0
    tracer.end("evaluate_results", decision=decision, elapsed=round(elapsed, 2))

    return {
        "retrieval_decision": decision,
        "should_web_search": decision == "NO_DATA",
        "current_step": "evaluate_results",
        "step_timings": {
            **state.get("step_timings", {}),
            "evaluate_results": round(elapsed, 3),
        },
    }


def _llm_evaluate(query: str, results: list[dict]) -> str:
    """Use fast LLM to evaluate retrieval sufficiency."""
    settings = get_settings()

    try:
        llm = ChatOllama(
            model=settings.ollama.model_fast,
            base_url=settings.ollama.base_url,
            temperature=0.0,
            num_ctx=4096,
        )

        # Build concise context summary
        snippets = []
        for r in results[:5]:
            snippets.append(r.get("content", "")[:200])
        context_summary = "\n---\n".join(snippets)

        messages = [
            SystemMessage(content=MULTI_HOP_RETRIEVER_PROMPT),
            HumanMessage(content=(
                f"Câu hỏi: {query}\n\n"
                f"Kết quả tìm kiếm ({len(results)} kết quả):\n{context_summary}"
            )),
        ]

        response = llm.invoke(messages)
        content = response.content.strip()

        # Parse decision
        try:
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                data = json.loads(content[json_start:json_end])
                return data.get("decision", "SUFFICIENT")
        except (json.JSONDecodeError, KeyError):
            pass

        # Fallback: look for keywords
        upper = content.upper()
        if "NO_DATA" in upper:
            return "NO_DATA"
        if "NEED_MORE" in upper:
            return "NEED_MORE"
        return "SUFFICIENT"

    except Exception:
        return "SUFFICIENT"  # Default to sufficient on error
