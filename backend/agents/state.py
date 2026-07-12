"""
BKAi Agent State Schema.

Defines the shared state TypedDict used across all agents
in the LangGraph workflow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, TypedDict

from tools.vector_search import SearchResult


class AgentState(TypedDict, total=False):
    """
    Shared state passed between all agents in the LangGraph pipeline.

    This is the single source of truth for the entire agent workflow.
    Each agent reads from and writes to specific fields.
    """

    # ── Input ──
    original_query: str                  # Raw user question
    chat_history: list[dict[str, str]]   # Previous conversation turns
    session_id: str                      # User session identifier
    query_id: str                        # Unique query run identifier

    # ── Query Processing ──
    rewritten_queries: list[str]         # Queries after rewriting
    hyde_document: str                   # Hypothetical document (HyDE)

    # ── Retrieval ──
    search_results: list[dict]           # Raw search results (serialized)
    reranked_results: list[dict]         # After cross-encoder reranking
    retrieval_context: str               # Formatted context for generation
    retrieval_hops: int                  # Number of retrieval iterations done
    retrieval_decision: str              # SUFFICIENT / NEED_MORE / NO_DATA

    # ── Generation ──
    generated_answer: str                # LLM-generated response
    answer_confidence: float             # Self-reflection confidence score
    answer_issues: list[str]             # Issues found by self-reflection

    # ── Control Flow ──
    current_step: str                    # Current agent step name
    error: str | None                    # Error message if any
    should_web_search: bool              # Whether to trigger web search
    iteration_count: int                 # Total agent loop iterations

    # ── Metrics ──
    step_timings: dict[str, float]       # Time taken per step (seconds)


def serialize_results(results: list[SearchResult]) -> list[dict]:
    """Convert SearchResult objects to serializable dicts for state."""
    return [
        {
            "content": r.content,
            "metadata": r.metadata,
            "score": r.score,
            "source": r.source,
        }
        for r in results
    ]


def deserialize_results(data: list[dict]) -> list[SearchResult]:
    """Convert serialized dicts back to SearchResult objects."""
    return [
        SearchResult(
            content=d["content"],
            metadata=d.get("metadata", {}),
            score=d.get("score", 0.0),
            source=d.get("source", "unknown"),
        )
        for d in data
    ]


def format_context(results: list[dict], max_chars: int = 4000) -> str:
    """
    Format search results into a context string for LLM generation.

    Includes metadata tags for source attribution.
    """
    parts: list[str] = []
    total_chars = 0

    for i, r in enumerate(results):
        source = r.get("metadata", {}).get("source_file", "unknown")
        category = r.get("metadata", {}).get("category", "")
        content = r["content"]

        block = f"[Nguồn {i+1}: {source} | {category}]\n{content}"

        if total_chars + len(block) > max_chars:
            remaining = max_chars - total_chars
            if remaining > 200:
                parts.append(block[:remaining] + "...")
            break

        parts.append(block)
        total_chars += len(block)

    return "\n\n---\n\n".join(parts)
