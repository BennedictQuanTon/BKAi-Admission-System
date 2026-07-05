"""
BKAi Vector Search Tool.

Provides semantic similarity search against the ChromaDB vector store
with metadata filtering support.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ingestion.embedder import get_chroma_client, get_embedding_model
from config.settings import get_settings
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SearchResult:
    """
    Standardized search result across all search tools.

    Attributes:
        content: The retrieved text chunk.
        metadata: Associated metadata (category, source, etc.).
        score: Relevance score (0-1, higher = more relevant).
        source: Which search tool produced this result.
    """

    content: str
    metadata: dict[str, str] = field(default_factory=dict)
    score: float = 0.0
    source: str = "vector"


def vector_search(
    query: str,
    top_k: int | None = None,
    filters: dict[str, str] | None = None,
) -> list[SearchResult]:
    """
    Perform semantic similarity search in ChromaDB.

    Args:
        query: Natural language search query.
        top_k: Number of results to return.
        filters: ChromaDB metadata filters (e.g., {"category": "tuyen_sinh"}).

    Returns:
        Ranked list of SearchResult objects.
    """
    settings = get_settings()
    k = top_k or settings.search.retrieval_top_k

    from ingestion.embedder import get_embedding_model, encode_query

    if "bge-m3" in settings.embedding.model.lower():
        query_embedding = [encode_query(query, return_sparse=False)[0]]
    else:
        model = get_embedding_model()
        query_embedding = model.encode([query], normalize_embeddings=True).tolist()
    client = get_chroma_client()
    collection = client.get_collection(settings.chroma.collection_name)

    where_clause = None
    if filters:
        conditions = []
        for key, value in filters.items():
            if value:
                conditions.append({key: {"$eq": value}})
        if len(conditions) == 1:
            where_clause = conditions[0]
        elif len(conditions) > 1:
            where_clause = {"$and": conditions}

    # Query ChromaDB
    try:
        results = collection.query(
            query_embeddings=query_embedding,
            n_results=min(k, collection.count()),
            where=where_clause,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as e:
        logger.error("vector_search_error", error=str(e), query=query[:100])
        # Retry without filters on error
        results = collection.query(
            query_embeddings=query_embedding,
            n_results=min(k, collection.count()),
            include=["documents", "metadatas", "distances"],
        )

    # Convert to SearchResult (cosine distance → similarity score)
    search_results: list[SearchResult] = []
    if results["documents"] and results["documents"][0]:
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            # ChromaDB cosine distance: 0 = identical, 2 = opposite
            # Convert to similarity score: 1 - (dist / 2)
            similarity = 1.0 - (dist / 2.0)
            search_results.append(SearchResult(
                content=doc,
                metadata=meta or {},
                score=round(similarity, 4),
                source="vector",
            ))

    logger.info(
        "vector_search_complete",
        query=query[:80],
        results=len(search_results),
        top_score=search_results[0].score if search_results else 0.0,
    )
    return search_results
