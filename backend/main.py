"""
BkAI — Agentic RAG Tư vấn Tuyển sinh ĐH Bách Khoa.
"""

from __future__ import annotations

import torch
torch.set_num_threads(2)

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import get_settings
from utils.logger import get_logger, setup_logging

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()

    setup_logging(log_level="DEBUG" if settings.api.debug else "INFO")
    logger.info(
        "bkai_startup",
        app_name=settings.app.name,
        gemini_primary=settings.gemini.model_primary,
        gemini_fast=settings.gemini.model_fast,
        api_port=settings.api.port,
    )

    try:
        from ingestion.embedder import get_embedding_model, get_bge_model
        if "bge-m3" in settings.embedding.model.lower():
            get_bge_model()
        else:
            get_embedding_model()
        logger.info("embedding_model_warmed")
    except Exception as e:
        logger.warning("embedding_warmup_failed", error=str(e))

    try:
        from workflows.main_graph import get_compiled_graph
        get_compiled_graph()
        logger.info("langgraph_warmed")
    except Exception as e:
        logger.warning("langgraph_warmup_failed", error=str(e))

    try:
        from memory.semantic_cache import get_redis_cache, get_redis_stats
        get_redis_cache().ping()
        get_redis_stats().ping()
        logger.info("redis_connected")
    except Exception as e:
        logger.warning("redis_connection_failed", error=str(e))

    yield
    logger.info("bkai_shutdown")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=f"{settings.app.name} — Tư vấn Tuyển sinh Bách Khoa",
        description="Agentic RAG system for HCMUT admissions counseling",
        version="2.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from api.routes import router
    app.include_router(router)

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
