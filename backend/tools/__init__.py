"""
BKAi Tools Package.

Provides search and retrieval integrations:
- vector_search: Semantic similarity via ChromaDB
- bm25_search: Lexical keyword matching via BM25
- hybrid_search: Combined semantic + lexical with RRF fusion
- reranker: Cross-encoder second-stage reranking
"""

from tools.vector_search import SearchResult, vector_search
from tools.bm25_search import bm25_search
from tools.hybrid_search import hybrid_search
from tools.reranker import rerank

__all__ = [
    "SearchResult",
    "vector_search",
    "bm25_search",
    "hybrid_search",
    "rerank",
]
