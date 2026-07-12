"""
BkAI Hybrid Search — ChromaDB + BM25.
"""

from __future__ import annotations

from config.settings import get_settings
from tools.bm25_search import bm25_search
from tools.vector_search import SearchResult, vector_search
from utils.logger import get_logger

logger = get_logger(__name__)
RRF_K = 60


def reciprocal_rank_fusion(
    result_lists: list[list[SearchResult]],
    k: int = RRF_K,
) -> list[SearchResult]:
    fusion_scores: dict[str, tuple[SearchResult, float]] = {}

    for results in result_lists:
        for rank, result in enumerate(results):
            content_key = result.content[:200]
            rrf_score = 1.0 / (k + rank + 1)
            if content_key in fusion_scores:
                existing_result, existing_score = fusion_scores[content_key]
                fusion_scores[content_key] = (existing_result, existing_score + rrf_score)
            else:
                fusion_scores[content_key] = (result, rrf_score)

    ranked = sorted(fusion_scores.values(), key=lambda x: x[1], reverse=True)
    return [
        SearchResult(
            content=result.content,
            metadata=result.metadata,
            score=round(score, 6),
            source="hybrid",
        )
        for result, score in ranked
    ]


def hybrid_search(
    query: str,
    top_k: int | None = None,
    alpha: float | None = None,
    filters: dict[str, str] | None = None,
) -> list[SearchResult]:
    settings = get_settings()
    k = top_k or settings.search.retrieval_top_k

    fetch_k = k * 2
    vector_results = vector_search(query, top_k=fetch_k, filters=filters)
    bm25_results = bm25_search(query, top_k=fetch_k)
    fused = reciprocal_rank_fusion([vector_results, bm25_results])
    return fused[:k]
