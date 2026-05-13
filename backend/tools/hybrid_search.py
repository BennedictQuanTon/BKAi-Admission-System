"""
BKAi Hybrid Search Engine.

Combines semantic (vector) search and lexical (BM25) search using
Reciprocal Rank Fusion (RRF) for robust retrieval.
"""

from __future__ import annotations

from config.settings import get_settings
from tools.vector_search import SearchResult, vector_search
from tools.bm25_search import bm25_search
from utils.logger import get_logger

logger = get_logger(__name__)

# RRF constant (standard value from literature)
RRF_K = 60


def reciprocal_rank_fusion(
    result_lists: list[list[SearchResult]],
    k: int = RRF_K,
) -> list[SearchResult]:
    """
    Merge multiple ranked lists using Reciprocal Rank Fusion.

    RRF score = Σ 1 / (k + rank_i) for each list where the doc appears.
    This is more robust than simple score averaging because it's
    invariant to score scale differences between search methods.

    Args:
        result_lists: Multiple ranked result lists to fuse.
        k: RRF constant (default 60).

    Returns:
        Merged and re-ranked list of SearchResult objects.
    """
    # Map content hash → (best SearchResult, accumulated RRF score)
    fusion_scores: dict[str, tuple[SearchResult, float]] = {}

    for results in result_lists:
        for rank, result in enumerate(results):
            # Use content as dedup key (first 200 chars to handle minor diffs)
            content_key = result.content[:200]
            rrf_score = 1.0 / (k + rank + 1)

            if content_key in fusion_scores:
                existing_result, existing_score = fusion_scores[content_key]
                fusion_scores[content_key] = (
                    existing_result,
                    existing_score + rrf_score,
                )
            else:
                fusion_scores[content_key] = (result, rrf_score)

    # Sort by fused score descending
    ranked = sorted(
        fusion_scores.values(),
        key=lambda x: x[1],
        reverse=True,
    )

    # Update scores to RRF scores and tag source as "hybrid"
    fused_results: list[SearchResult] = []
    for result, rrf_score in ranked:
        fused_results.append(SearchResult(
            content=result.content,
            metadata=result.metadata,
            score=round(rrf_score, 6),
            source="hybrid",
        ))

    return fused_results


def hybrid_search(
    query: str,
    top_k: int | None = None,
    alpha: float | None = None,
    filters: dict[str, str] | None = None,
) -> list[SearchResult]:
    """
    Perform hybrid search combining semantic + lexical retrieval.

    Uses Reciprocal Rank Fusion to merge results from both search
    methods, then returns the top-K fused results.

    Args:
        query: Natural language search query.
        top_k: Final number of results to return.
        alpha: Not used with RRF (kept for API compatibility).
        filters: Metadata filters passed to vector search.

    Returns:
        Fused and ranked list of SearchResult objects.
    """
    settings = get_settings()
    k = top_k or settings.search.retrieval_top_k

    # Fetch from both search engines (over-fetch for better fusion)
    fetch_k = k * 2

    vector_results = vector_search(query, top_k=fetch_k, filters=filters)
    bm25_results = bm25_search(query, top_k=fetch_k)

    # Fuse results
    fused = reciprocal_rank_fusion([vector_results, bm25_results])

    # Trim to requested top_k
    final_results = fused[:k]

    logger.info(
        "hybrid_search_complete",
        query=query[:80],
        vector_count=len(vector_results),
        bm25_count=len(bm25_results),
        fused_count=len(final_results),
        top_score=final_results[0].score if final_results else 0.0,
    )
    return final_results
