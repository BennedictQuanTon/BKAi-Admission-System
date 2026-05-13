"""
BKAi — Agentic RAG Tư vấn Tuyển sinh ĐH Bách Khoa.

FastAPI application entry point.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import get_settings
from utils.logger import setup_logging, get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup and shutdown lifecycle manager."""
    settings = get_settings()

    # ── Startup ──
    setup_logging(log_level="DEBUG" if settings.api.debug else "INFO")
    logger.info(
        "bkai_startup",
        ollama_model=settings.ollama.model_primary,
        api_port=settings.api.port,
    )

    # Warm up embedding model (background)
    try:
        from ingestion.embedder import get_embedding_model
        get_embedding_model()
        logger.info("embedding_model_warmed")
    except Exception as e:
        logger.warning("embedding_warmup_failed", error=str(e))

    # Compile LangGraph
    try:
        from workflows.main_graph import get_compiled_graph
        get_compiled_graph()
        logger.info("langgraph_warmed")
    except Exception as e:
        logger.warning("langgraph_warmup_failed", error=str(e))

    # Verify Redis
    try:
        from memory.semantic_cache import get_redis_cache, get_redis_stats
        get_redis_cache().ping()
        get_redis_stats().ping()
        logger.info("redis_connected")
    except Exception as e:
        logger.warning("redis_connection_failed", error=str(e))

    yield

    # ── Shutdown ──
    logger.info("bkai_shutdown")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="BKAi — Tư vấn Tuyển sinh Bách Khoa",
        description="Agentic RAG system for HCMUT admissions counseling",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register REST routes
    from api.routes import router
    app.include_router(router)

    # Register WebSocket routes
    from api.websocket import ws_router
    app.include_router(ws_router)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "main:app",
        host=settings.api.host,
        port=settings.api.port,
        reload=True,
        log_level="info",
    )
