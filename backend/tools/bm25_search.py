"""
BKAi BM25 Lexical Search Tool.

Provides keyword-based search using BM25Okapi for exact term matching,
complementing the semantic vector search.
"""

from __future__ import annotations

import pickle

import numpy as np

from config.settings import get_settings
from tools.vector_search import SearchResult
from utils.logger import get_logger
from utils.vietnamese import tokenize_vi

logger = get_logger(__name__)

# ──────────────────────────────────────────────
# Singleton cache
# ──────────────────────────────────────────────
_bm25_index = None
_bm25_chunks: list[dict] | None = None


def _load_bm25():
    """Load BM25 index and chunks from disk (lazy, cached)."""
    global _bm25_index, _bm25_chunks

    if _bm25_index is not None:
        return

    settings = get_settings()
    index_path = settings.processed_data_dir / "bm25_index.pkl"
    chunks_path = settings.processed_data_dir / "bm25_chunks.pkl"

    if not index_path.exists() or not chunks_path.exists():
        raise FileNotFoundError(
            f"BM25 index not found at {index_path}. Run 'python ingest.py' first."
        )

    with open(index_path, "rb") as f:
        _bm25_index = pickle.load(f)

    with open(chunks_path, "rb") as f:
        _bm25_chunks = pickle.load(f)

    logger.info("bm25_index_loaded", chunks=len(_bm25_chunks))


def bm25_search(
    query: str,
    top_k: int | None = None,
) -> list[SearchResult]:
    """
    Perform BM25 lexical search.

    Args:
        query: Search query (will be tokenized by whitespace).
        top_k: Number of results to return.

    Returns:
        Ranked list of SearchResult objects.
    """
    settings = get_settings()
    k = top_k or settings.search.retrieval_top_k

    _load_bm25()

    # Tokenize query (simple whitespace split for Vietnamese)
    tokens = tokenize_vi(query)
    if not tokens:
        return []

    # Get BM25 scores
    scores = _bm25_index.get_scores(tokens)

    # Get top-K indices
    top_indices = np.argsort(scores)[-k:][::-1]

    # Filter out zero-score results
    results: list[SearchResult] = []
    max_score = scores[top_indices[0]] if len(top_indices) > 0 else 1.0

    for idx in top_indices:
        if scores[idx] <= 0:
            continue

        chunk = _bm25_chunks[idx]
        # Normalize score to 0-1 range
        normalized = scores[idx] / max(max_score, 1e-6)

        results.append(SearchResult(
            content=chunk["content"],
            metadata=chunk["metadata"],
            score=round(float(normalized), 4),
            source="bm25",
        ))

    logger.info(
        "bm25_search_complete",
        query=query[:80],
        results=len(results),
        top_score=results[0].score if results else 0.0,
    )
    return results
