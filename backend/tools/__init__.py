"""
BKAi Tools Package.

Provides search, retrieval, and external tool integrations:
- vector_search: Semantic similarity via ChromaDB
- bm25_search: Lexical keyword matching via BM25
- hybrid_search: Combined semantic + lexical with RRF fusion
- reranker: Cross-encoder second-stage reranking
- web_search: Domain-restricted web scraping fallback
"""

from tools.vector_search import SearchResult, vector_search
from tools.bm25_search import bm25_search
from tools.hybrid_search import hybrid_search
from tools.reranker import rerank
from tools.web_search import web_search

__all__ = [
    "SearchResult",
    "vector_search",
    "bm25_search",
    "hybrid_search",
    "rerank",
    "web_search",
]
