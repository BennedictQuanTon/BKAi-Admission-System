"""
BKAi Agent State Schema.
"""

from __future__ import annotations

from typing import TypedDict

from tools.vector_search import SearchResult


class AgentState(TypedDict, total=False):
    # ── Input ──
    original_query: str
    chat_history: list[dict[str, str]]
    session_id: str
    query_id: str
    channel: str  # chat | voice
    student_profile: dict

    # ── Query Processing / Counselor ──
    resolved_query: str
    rewritten_queries: list[str]
    hyde_document: str
    counselor_action: str  # ASK_CLARIFY | RETRIEVE | ADVISE
    clarify_question: str
    profile_patch: dict

    # ── Retrieval ──
    search_results: list[dict]
    reranked_results: list[dict]
    retrieval_context: str
    retrieval_hops: int
    retrieval_decision: str

    # ── Generation ──
    generated_answer: str
    answer_confidence: float
    answer_issues: list[str]

    # ── Control Flow ──
    current_step: str
    error: str | None
    iteration_count: int

    # ── Metrics ──
    step_timings: dict[str, float]


def serialize_results(results: list[SearchResult]) -> list[dict]:
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
