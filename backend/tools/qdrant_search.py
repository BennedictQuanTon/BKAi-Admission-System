"""
BkAI Qdrant hybrid search — dense + sparse (BGE-M3) with RRF.
"""

from __future__ import annotations

from qdrant_client import QdrantClient, models

from config.settings import get_settings
from ingestion.embedder import encode_query, get_embedding_dimension, get_qdrant_client
from tools.vector_search import SearchResult
from utils.logger import get_logger

logger = get_logger(__name__)

_collection_ready = False


def ensure_qdrant_collection() -> None:
    global _collection_ready
    if _collection_ready:
        return

    settings = get_settings()
    client = get_qdrant_client()
    name = settings.qdrant.collection_name
    dim = get_embedding_dimension()

    if client.collection_exists(name):
        _collection_ready = True
        return

    client.create_collection(
        collection_name=name,
        vectors_config={
            "dense": models.VectorParams(size=dim, distance=models.Distance.COSINE),
        },
        sparse_vectors_config={
            "sparse": models.SparseVectorParams(
                index=models.SparseIndexParams(on_disk=False),
            ),
        },
    )
    logger.info("qdrant_collection_created", name=name, dim=dim)
    _collection_ready = True


def qdrant_hybrid_search(
    query: str,
    top_k: int | None = None,
) -> list[SearchResult]:
    settings = get_settings()
    k = top_k or settings.search.retrieval_top_k
    ensure_qdrant_collection()

    dense, sparse = encode_query(query, return_sparse=True)
    client = get_qdrant_client()
    name = settings.qdrant.collection_name

    if client.count(name, exact=True).count == 0:
        logger.warning("qdrant_empty_collection")
        return []

    sparse_vec = models.SparseVector(
        indices=list(sparse.keys()),
        values=list(sparse.values()),
    )

    response = client.query_points(
        collection_name=name,
        prefetch=[
            models.Prefetch(query=dense, using="dense", limit=k * 2),
            models.Prefetch(query=sparse_vec, using="sparse", limit=k * 2),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        limit=k,
        with_payload=True,
    )

    results: list[SearchResult] = []
    for point in response.points:
        payload = point.payload or {}
        results.append(SearchResult(
            content=payload.get("content", ""),
            metadata={key: str(val) for key, val in payload.items() if key != "content"},
            score=round(float(point.score or 0.0), 4),
            source="qdrant_hybrid",
        ))

    logger.info("qdrant_search_complete", query=query[:80], results=len(results))
    return results
