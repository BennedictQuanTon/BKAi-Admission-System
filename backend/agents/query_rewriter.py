"""
BkAI Query Rewriting Agent — Gemini Flash-Lite with structured output.
"""

from __future__ import annotations

import time

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agents.state import AgentState
from config.prompts import QUERY_REWRITER_PROMPT
from services.llm_factory import acquire_rpm_slot, get_fast_llm
from utils.logger import AgentTracer

from api.dashboard_manager import stream_progress

tracer = AgentTracer("query_rewriter")


class RewriteOutput(BaseModel):
    rewritten_queries: list[str] = Field(default_factory=list)
    hyde_document: str = ""


async def query_rewrite_node(state: AgentState) -> dict:
    t0 = time.time()
    query = state["original_query"]
    session_id = state.get("session_id", "")
    query_id = state.get("query_id", "")

    stream_progress(
        session_id=session_id,
        query_id=query_id,
        step="query_rewrite",
        status="running",
        message="Analyzing and optimizing query (Query Rewrite)...",
        query=query,
    )
    tracer.start("rewrite", query=query[:80])

    try:
        await acquire_rpm_slot("fast")
        llm = get_fast_llm().with_structured_output(RewriteOutput)
        result: RewriteOutput = await llm.ainvoke([
            SystemMessage(content=QUERY_REWRITER_PROMPT),
            HumanMessage(content=f"Câu hỏi gốc: {query}"),
        ])
        queries = list(result.rewritten_queries or [])
        if query not in queries:
            queries.insert(0, query)
        rewritten = {
            "rewritten_queries": queries[:3],
            "hyde_document": result.hyde_document or "",
        }
    except Exception as e:
        tracer.error("rewrite", error=str(e))
        rewritten = {"rewritten_queries": [query], "hyde_document": ""}

    elapsed = time.time() - t0
    tracer.end("rewrite", elapsed=round(elapsed, 2))

    queries_str = ", ".join(f"'{q}'" for q in rewritten["rewritten_queries"])
    stream_progress(
        session_id=session_id,
        query_id=query_id,
        step="query_rewrite",
        status="done",
        message=f"Query rewrite completed in {elapsed:.2f}s. Rewritten queries: {queries_str}",
        elapsed=round(elapsed, 3),
    )

    return {
        "rewritten_queries": rewritten["rewritten_queries"],
        "hyde_document": rewritten.get("hyde_document", ""),
        "current_step": "query_rewrite",
        "step_timings": {
            **state.get("step_timings", {}),
            "query_rewrite": round(elapsed, 3),
        },
    }
