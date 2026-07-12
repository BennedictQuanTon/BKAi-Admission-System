"""
BKAi Semantic Cache (Redis).

Caches Q&A pairs with semantic similarity matching.
Liked answers are promoted to reusable cache.
"""

from __future__ import annotations

import json
import time
import hashlib

import numpy as np
import redis

from config.settings import get_settings
from ingestion.embedder import encode_query
from utils.logger import get_logger

logger = get_logger(__name__)

_redis_cache: redis.Redis | None = None
_redis_stats: redis.Redis | None = None

CACHE_PREFIX = "bkai:cache:"
STATS_PREFIX = "bkai:stats:"
QUESTIONS_KEY = "bkai:questions"
HISTORY_KEY = "bkai:stats_history"
ERRORS_KEY = "bkai:errors"


def _strip_db_from_url(url: str) -> str:
    """Strip the DB number from a Redis URL so that the explicit db= kwarg is honored.

    redis.Redis.from_url() silently ignores the db kwarg when the URL
    already contains a path like /0.  Stripping it avoids that pitfall.
    """
    from urllib.parse import urlparse, urlunparse

    parsed = urlparse(url)
    # Remove path that looks like a DB number (e.g., /0, /1, /2)
    if parsed.path and parsed.path.strip("/").isdigit():
        parsed = parsed._replace(path="")
    return urlunparse(parsed)


def get_redis_cache() -> redis.Redis:
    """Get Redis client for semantic cache (DB 1)."""
    global _redis_cache
    if _redis_cache is None:
        settings = get_settings()
        base_url = _strip_db_from_url(settings.redis.url)
        _redis_cache = redis.Redis.from_url(
            base_url,
            db=settings.redis.cache_db,
            decode_responses=True,
        )
        logger.info("redis_cache_connected", db=settings.redis.cache_db)
    return _redis_cache


def get_redis_stats() -> redis.Redis:
    """Get Redis client for stats tracking (DB 2)."""
    global _redis_stats
    if _redis_stats is None:
        settings = get_settings()
        base_url = _strip_db_from_url(settings.redis.url)
        _redis_stats = redis.Redis.from_url(
            base_url,
            db=settings.redis.stats_db,
            decode_responses=True,
        )
        logger.info("redis_stats_connected", db=settings.redis.stats_db)
    return _redis_stats


def _embed_query(query: str) -> list[float]:
    """Embed a query for cache similarity comparison."""
    if "bge-m3" in get_settings().embedding.model.lower():
        return encode_query(query, return_sparse=False)[0]
    from ingestion.embedder import get_embedding_model
    model = get_embedding_model()
    return model.encode([query], normalize_embeddings=True).tolist()[0]


def _cosine_sim(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    a_np = np.array(a)
    b_np = np.array(b)
    return float(np.dot(a_np, b_np) / (np.linalg.norm(a_np) * np.linalg.norm(b_np) + 1e-9))


def check_cache(query: str) -> dict | None:
    """
    Check semantic cache for a similar question.

    Returns cached answer if:
    1. A similar question exists (cosine >= threshold)
    2. AND that answer has been liked (status = "liked")

    Returns None on cache miss.
    """
    settings = get_settings()
    threshold = settings.cache.semantic_cache_threshold
    r = get_redis_cache()

    try:
        query_emb = _embed_query(query)

        from memory.redis_vector_cache import vector_cache_search, ensure_vector_index
        if ensure_vector_index(r):
            vector_hit = vector_cache_search(r, query_emb, threshold)
            if vector_hit:
                logger.info("cache_hit", similarity=vector_hit.get("similarity"))
                return vector_hit
            # If the vector search index is functional but returned None, it is a genuine cache miss.
            return None

        # Legacy fallback scan (only run if vector index is unavailable)
        logger.warning("vector_index_unavailable_running_legacy_fallback")
        keys = r.keys(f"{CACHE_PREFIX}*")
        best_match = None
        best_sim = 0.0

        for key in keys:
            data = r.get(key)
            if not data:
                continue
            entry = json.loads(data)

            # Only return liked answers
            if entry.get("status") != "liked":
                continue

            cached_emb = entry.get("embedding")
            if not cached_emb:
                continue

            sim = _cosine_sim(query_emb, cached_emb)
            if sim > best_sim and sim >= threshold:
                best_sim = sim
                best_match = entry

        if best_match:
            logger.info("cache_hit", similarity=round(best_sim, 4))
            return {
                "answer": best_match["answer"],
                "confidence": best_match.get("confidence", 1.0),
                "cached": True,
                "similarity": round(best_sim, 4),
            }

    except Exception as e:
        logger.warning("cache_check_error", error=str(e))

    return None


def store_in_cache(
    query: str,
    answer: str,
    confidence: float = 0.0,
    timings: dict | None = None,
    sources: list[str] | None = None,
) -> str:
    """
    Store a Q&A pair in the semantic cache.

    Initial status is "unrated". Becomes "liked" or "disliked"
    after user feedback.

    Returns the cache key.
    """
    settings = get_settings()
    r = get_redis_cache()

    try:
        query_emb = _embed_query(query)
        cache_key = f"{CACHE_PREFIX}{hashlib.md5(query.encode()).hexdigest()}"
        payload = {
            "timings": timings or {},
            "sources": sources or [],
            "timestamp": time.time(),
        }

        from memory.redis_vector_cache import vector_cache_store
        vector_cache_store(
            r,
            cache_key,
            query,
            answer,
            query_emb,
            confidence,
            settings.cache.cache_ttl_unrated,
            payload,
        )

        # Keep JSON copy for feedback updates
        entry = {
            "query": query,
            "answer": answer,
            "embedding": query_emb,
            "confidence": confidence,
            "status": "unrated",
            "timestamp": time.time(),
            "timings": timings or {},
            "sources": sources or [],
        }
        r.setex(
            f"{cache_key}:meta",
            settings.cache.cache_ttl_unrated,
            json.dumps(entry, ensure_ascii=False),
        )

        logger.info("cache_stored", key=cache_key[-12:])
        return cache_key

    except Exception as e:
        logger.warning("cache_store_error", error=str(e))
        return ""


def update_feedback(query: str, feedback: str) -> bool:
    """
    Update cache entry with user feedback.

    - "like": Promotes to reusable cache with longer TTL.
    - "dislike": Marks as rejected.
    """
    settings = get_settings()
    r = get_redis_cache()

    try:
        cache_key = f"{CACHE_PREFIX}{hashlib.md5(query.encode()).hexdigest()}"
        data = r.get(f"{cache_key}:meta") or r.get(cache_key)
        if not data:
            return False

        entry = json.loads(data) if isinstance(data, str) else json.loads(data)
        entry["status"] = "liked" if feedback == "like" else "disliked"
        entry["feedback_time"] = time.time()
        ttl = (
            settings.cache.cache_ttl_liked
            if feedback == "like"
            else settings.cache.cache_ttl_unrated
        )

        r.setex(f"{cache_key}:meta", ttl, json.dumps(entry, ensure_ascii=False))
        if r.exists(cache_key):
            r.hset(cache_key, mapping={"status": entry["status"]})
            r.expire(cache_key, ttl)
        logger.info("feedback_updated", feedback=feedback, key=cache_key[-12:])
        return True

    except Exception as e:
        logger.warning("feedback_error", error=str(e))
        return False


# ──────────────────────────────────────────────
# Stats Tracking
# ──────────────────────────────────────────────
def record_question(
    query: str,
    answer: str,
    response_time: float,
    build_time: float,
    cached: bool = False,
    feedback: str = "unrated",
    trace: dict | None = None,
    question_id: str | None = None,
) -> None:
    """Record a question event for dashboard stats."""
    import uuid
    r = get_redis_stats()

    try:
        entry = {
            "id": question_id or str(uuid.uuid4()),
            "query": query[:200],
            "answer": answer[:200],
            "response_time": response_time,
            "build_time": build_time,
            "cached": cached,
            "feedback": feedback,
            "trace": trace or {},
            "timestamp": time.time(),
        }

        # Push to recent questions list (keep last 100)
        r.lpush(QUESTIONS_KEY, json.dumps(entry, ensure_ascii=False))
        r.ltrim(QUESTIONS_KEY, 0, 99)

        # Increment counters
        r.incr(f"{STATS_PREFIX}total")
        if cached:
            r.incr(f"{STATS_PREFIX}cache_hits")

        # Track response times
        r.lpush(f"{STATS_PREFIX}response_times", str(response_time))
        r.ltrim(f"{STATS_PREFIX}response_times", 0, 99)
        r.lpush(f"{STATS_PREFIX}build_times", str(build_time))
        r.ltrim(f"{STATS_PREFIX}build_times", 0, 99)

        record_stats_snapshot()

    except Exception as e:
        logger.warning("stats_record_error", error=str(e))


def update_question_feedback(query: str, feedback: str) -> None:
    """Update feedback counter in stats."""
    r = get_redis_stats()
    try:
        if feedback == "like":
            r.incr(f"{STATS_PREFIX}liked")
        elif feedback == "dislike":
            r.incr(f"{STATS_PREFIX}disliked")
    except Exception as e:
        logger.warning("stats_feedback_error", error=str(e))


def evaluate_question_by_id(question_id: str, feedback: str) -> bool:
    """Finds a question by ID, updates its feedback rating, and updates counters."""
    r = get_redis_stats()
    try:
        elements = r.lrange(QUESTIONS_KEY, 0, -1)
        for idx, elem in enumerate(elements):
            item = json.loads(elem)
            if item.get("id") == question_id:
                old_feedback = item.get("feedback", "unrated")
                if old_feedback == feedback:
                    return True

                item["feedback"] = feedback
                r.lset(QUESTIONS_KEY, idx, json.dumps(item, ensure_ascii=False))

                if old_feedback == "unrated":
                    r.decr(f"{STATS_PREFIX}unrated")
                elif old_feedback == "like":
                    r.decr(f"{STATS_PREFIX}liked")
                elif old_feedback == "dislike":
                    r.decr(f"{STATS_PREFIX}disliked")

                if feedback == "like":
                    r.incr(f"{STATS_PREFIX}liked")
                elif feedback == "dislike":
                    r.incr(f"{STATS_PREFIX}disliked")

                record_stats_snapshot()
                return True
        return False
    except Exception as e:
        logger.warning("evaluate_question_by_id_error", error=str(e))
        return False


def record_stats_snapshot() -> None:
    """Save a point-in-time stats snapshot for trend charts."""
    r = get_redis_stats()
    try:
        stats = get_stats()
        snapshot = {
            "total": stats["total_questions"],
            "liked": stats["liked"],
            "disliked": stats["disliked"],
            "cache_hit_rate": stats["cache_hit_rate"],
            "avg_response_time": stats["avg_response_time"],
        }
        timestamp = time.time()
        r.zadd(HISTORY_KEY, {json.dumps(snapshot): timestamp})
        # Keep last 24h only (1440 data points max if every minute)
        cutoff = timestamp - 86400
        r.zremrangebyscore(HISTORY_KEY, "-inf", cutoff)
    except Exception as e:
        logger.warning("stats_snapshot_error", error=str(e))


def get_stats_history(hours: int = 24) -> list[dict]:
    """Get stats history for the last N hours."""
    r = get_redis_stats()
    try:
        cutoff = time.time() - (hours * 3600)
        raw = r.zrangebyscore(HISTORY_KEY, cutoff, "+inf", withscores=True)
        return [
            {**json.loads(data), "timestamp": score}
            for data, score in raw
        ]
    except Exception as e:
        logger.warning("stats_history_error", error=str(e))
        return []


def record_error(error_type: str, message: str) -> None:
    """Record a system error for dashboard monitoring."""
    r = get_redis_stats()
    try:
        entry = {
            "type": error_type,
            "message": message[:200],
            "timestamp": time.time(),
        }
        r.lpush(ERRORS_KEY, json.dumps(entry, ensure_ascii=False))
        r.ltrim(ERRORS_KEY, 0, 49)  # Keep last 50 errors
        r.incr(f"{STATS_PREFIX}errors")
    except Exception as e:
        logger.warning("record_error_failed", error=str(e))


def get_stats() -> dict:
    """Get aggregated stats for the dashboard."""
    r = get_redis_stats()

    try:
        total = int(r.get(f"{STATS_PREFIX}total") or 0)
        liked = int(r.get(f"{STATS_PREFIX}liked") or 0)
        disliked = int(r.get(f"{STATS_PREFIX}disliked") or 0)
        cache_hits = int(r.get(f"{STATS_PREFIX}cache_hits") or 0)
        error_count = int(r.get(f"{STATS_PREFIX}errors") or 0)

        # Compute averages
        resp_times = r.lrange(f"{STATS_PREFIX}response_times", 0, -1)
        build_times = r.lrange(f"{STATS_PREFIX}build_times", 0, -1)

        avg_resp = (
            sum(float(t) for t in resp_times) / len(resp_times)
            if resp_times else 0.0
        )
        avg_build = (
            sum(float(t) for t in build_times) / len(build_times)
            if build_times else 0.0
        )

        # Recent questions
        raw_recent = r.lrange(QUESTIONS_KEY, 0, 19)
        recent = [json.loads(q) for q in raw_recent]

        # Recent errors
        raw_errors = r.lrange(ERRORS_KEY, 0, 4)
        recent_errors = [json.loads(e) for e in raw_errors] if raw_errors else []

        return {
            "total_questions": total,
            "liked": liked,
            "disliked": disliked,
            "unrated": max(0, total - liked - disliked),
            "avg_response_time": round(avg_resp, 2),
            "avg_build_time": round(avg_build, 2),
            "cache_hit_rate": round(cache_hits / max(total, 1), 4),
            "error_count": error_count,
            "recent_errors": recent_errors,
            "recent_questions": recent,
        }

    except Exception as e:
        logger.warning("stats_get_error", error=str(e))
        return {"total_questions": 0, "liked": 0, "disliked": 0, "unrated": 0, "error_count": 0, "recent_errors": []}
