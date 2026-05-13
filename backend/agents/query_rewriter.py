"""
BKAi Query Rewriting Agent.

Rewrites user queries for optimal retrieval using:
- Clarity expansion (adding context)
- HyDE (Hypothetical Document Embeddings)
- Abbreviation expansion
"""

from __future__ import annotations

import json
import time

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_ollama import ChatOllama

from agents.state import AgentState
from config.settings import get_settings
from config.prompts import QUERY_REWRITER_PROMPT
from utils.logger import AgentTracer

tracer = AgentTracer("query_rewriter")


def query_rewrite_node(state: AgentState) -> dict:
    """
    LangGraph node: Rewrite the user query for better retrieval.

    Uses the fast model (llama3.2) for speed since query
    rewriting is a relatively simple task.

    Returns partial state update with rewritten_queries and hyde_document.
    """
    t0 = time.time()
    query = state["original_query"]
    tracer.start("rewrite", query=query[:80])

    settings = get_settings()

    try:
        llm = ChatOllama(
            model=settings.ollama.model_fast,
            base_url=settings.ollama.base_url,
            temperature=0.3,
            num_ctx=4096,
        )

        messages = [
            SystemMessage(content=QUERY_REWRITER_PROMPT),
            HumanMessage(content=f"Câu hỏi gốc: {query}"),
        ]

        response = llm.invoke(messages)
        content = response.content.strip()

        # Parse JSON response
        rewritten = _parse_rewrite_response(content, query)

    except Exception as e:
        tracer.error("rewrite", error=str(e))
        # Fallback: use original query
        rewritten = {
            "rewritten_queries": [query],
            "hyde_document": "",
        }

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


def _parse_rewrite_response(content: str, original: str) -> dict:
    """Parse LLM response, extracting rewritten queries."""
    # Try JSON parsing first
    try:
        # Find JSON block in response
        json_start = content.find("{")
        json_end = content.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            data = json.loads(content[json_start:json_end])
            queries = data.get("rewritten_queries", [original])
            hyde = data.get("hyde_document", "")
            # Always include original query
            if original not in queries:
                queries.insert(0, original)
            return {"rewritten_queries": queries[:3], "hyde_document": hyde}
    except (json.JSONDecodeError, KeyError):
        pass

    # Fallback: use original + cleaned response as a second query
    cleaned = content.replace("\n", " ").strip()[:200]
    queries = [original]
    if cleaned and cleaned != original:
        queries.append(cleaned)

    return {"rewritten_queries": queries, "hyde_document": ""}
