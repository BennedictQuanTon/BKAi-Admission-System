"""
BKAi Cross-Encoder Reranker.

Reranks candidate search results using a cross-encoder model
for more accurate relevance scoring than bi-encoder similarity.
"""

from __future__ import annotations

from sentence_transformers import CrossEncoder

from config.settings import get_settings
from tools.vector_search import SearchResult
from utils.logger import get_logger

logger = get_logger(__name__)

# ──────────────────────────────────────────────
# Singleton
# ──────────────────────────────────────────────
_reranker: CrossEncoder | None = None

# Lightweight cross-encoder optimized for speed
RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


def get_reranker() -> CrossEncoder:
    """Get or initialize the cross-encoder reranker (singleton)."""
    global _reranker
    if _reranker is None:
        logger.info("loading_reranker", model=RERANKER_MODEL)
        _reranker = CrossEncoder(RERANKER_MODEL, max_length=512)
        logger.info("reranker_loaded", model=RERANKER_MODEL)
    return _reranker


def rerank(
    query: str,
    results: list[SearchResult],
    top_k: int | None = None,
) -> list[SearchResult]:
    """
    Rerank search results using a cross-encoder model.

    The cross-encoder jointly encodes (query, document) pairs,
    producing more accurate relevance scores than the initial
    bi-encoder retrieval stage.

    Args:
        query: The original user query.
        results: Candidate search results to rerank.
        top_k: Number of top results to return after reranking.

    Returns:
        Reranked list of SearchResult objects.
    """
    if not results:
        return []

    settings = get_settings()
    k = top_k or settings.search.rerank_top_k

    reranker_model = get_reranker()

    # Create (query, document) pairs for cross-encoder
    pairs = [(query, r.content) for r in results]

    # Score all pairs
    scores = reranker_model.predict(pairs, show_progress_bar=False)

    # Attach scores and sort
    scored_results: list[tuple[float, SearchResult]] = []
    for score, result in zip(scores, results):
        scored_results.append((float(score), result))

    scored_results.sort(key=lambda x: x[0], reverse=True)

    # Build final results with updated scores
    reranked: list[SearchResult] = []
    for score, result in scored_results[:k]:
        reranked.append(SearchResult(
            content=result.content,
            metadata=result.metadata,
            score=round(score, 4),
            source=f"{result.source}+reranked",
        ))

    logger.info(
        "rerank_complete",
        query=query[:80],
        input_count=len(results),
        output_count=len(reranked),
        top_score=reranked[0].score if reranked else 0.0,
    )
    return reranked
