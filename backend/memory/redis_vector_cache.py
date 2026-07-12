"""Redis Stack vector index helpers for semantic cache."""

from __future__ import annotations

import json
import struct

import redis
from redis.commands.search.field import TagField, TextField, VectorField
from redis.commands.search.index_definition import IndexDefinition, IndexType
from redis.commands.search.query import Query

from config.settings import get_settings
from ingestion.embedder import get_embedding_dimension
from utils.logger import get_logger

logger = get_logger(__name__)

VECTOR_INDEX = "idx:bkai_cache"
_index_ready = False


def _embedding_bytes(vector: list[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


def ensure_vector_index(r: redis.Redis) -> bool:
    global _index_ready
    if _index_ready:
        return True

    try:
        r.ft(VECTOR_INDEX).info()
        _index_ready = True
        return True
    except redis.exceptions.ResponseError:
        pass

    try:
        dim = get_embedding_dimension()
        schema = (
            TagField("status"),
            TextField("query"),
            TextField("answer"),
            TextField("confidence"),
            TextField("payload"),
            VectorField(
                "embedding",
                "HNSW",
                {"TYPE": "FLOAT32", "DIM": dim, "DISTANCE_METRIC": "COSINE"},
            ),
        )
        r.ft(VECTOR_INDEX).create_index(
            schema,
            definition=IndexDefinition(prefix=["bkai:cache:"], index_type=IndexType.HASH),
        )
        _index_ready = True
        logger.info("redis_vector_index_created", dim=dim)
        return True
    except Exception as e:
        logger.warning("redis_vector_index_unavailable", error=str(e))
        return False


def vector_cache_search(r: redis.Redis, query_embedding: list[float], threshold: float) -> dict | None:
    if not ensure_vector_index(r):
        return None

    try:
        q = (
            Query("@status:{liked}=>[KNN 8 @embedding $vec AS score]")
            .sort_by("score")
            .return_fields("query", "answer", "confidence", "payload", "score")
            .dialect(2)
        )
        results = r.ft(VECTOR_INDEX).search(
            q,
            query_params={"vec": _embedding_bytes(query_embedding)},
        )

        if not results.docs:
            return None

        best = results.docs[0]
        distance = float(best.score)
        similarity = 1.0 - distance
        if similarity < threshold:
            return None

        payload = json.loads(best.payload) if getattr(best, "payload", None) else {}
        return {
            "answer": best.answer,
            "confidence": float(best.confidence or payload.get("confidence", 1.0)),
            "cached": True,
            "similarity": round(similarity, 4),
        }
    except Exception as e:
        logger.warning("redis_vector_search_error", error=str(e))
        return None


def vector_cache_store(
    r: redis.Redis,
    cache_key: str,
    query: str,
    answer: str,
    query_embedding: list[float],
    confidence: float,
    ttl: int,
    payload: dict,
) -> None:
    if ensure_vector_index(r):
        r.hset(
            cache_key,
            mapping={
                "query": query,
                "answer": answer,
                "status": "unrated",
                "confidence": str(confidence),
                "payload": json.dumps(payload, ensure_ascii=False),
                "embedding": _embedding_bytes(query_embedding),
            },
        )
        r.expire(cache_key, ttl)
        return

    entry = {
        "query": query,
        "answer": answer,
        "embedding": query_embedding,
        "confidence": confidence,
        "status": "unrated",
        "payload": payload,
    }
    r.setex(cache_key, ttl, json.dumps(entry, ensure_ascii=False))
