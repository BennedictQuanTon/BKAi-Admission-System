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

tracer = AgentTracer("query_rewriter")


class RewriteOutput(BaseModel):
    rewritten_queries: list[str] = Field(default_factory=list)
    hyde_document: str = ""


async def query_rewrite_node(state: AgentState) -> dict:
    t0 = time.time()
    query = state["original_query"]
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

    return {
        "rewritten_queries": rewritten["rewritten_queries"],
        "hyde_document": rewritten.get("hyde_document", ""),
        "current_step": "query_rewrite",
        "step_timings": {
            **state.get("step_timings", {}),
            "query_rewrite": round(elapsed, 3),
        },
    }
