"""
BKAi Backend Configuration Module.

Centralized settings management using Pydantic BaseSettings.
All configuration is loaded from environment variables and .env file.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ──────────────────────────────────────────────
# Path Constants
# ──────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
DATA_DIR = BACKEND_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
CSV_DATA_DIR = DATA_DIR / "csv"
PROCESSED_DATA_DIR = DATA_DIR / "processed"


class OllamaSettings(BaseSettings):
    """Ollama LLM configuration."""

    model_config = SettingsConfigDict(env_prefix="OLLAMA_")

    base_url: str = "http://localhost:11434"
    model_primary: str = "qwen2.5:7b"
    model_fast: str = "llama3.2"
    request_timeout: int = 120
    num_ctx: int = 8192


class RedisSettings(BaseSettings):
    """Redis connection configuration."""

    model_config = SettingsConfigDict(env_prefix="REDIS_")

    url: str = "redis://localhost:6379/0"
    cache_db: int = 1
    stats_db: int = 2
    max_connections: int = 20


class ChromaSettings(BaseSettings):
    """ChromaDB vector store configuration."""

    model_config = SettingsConfigDict(env_prefix="CHROMA_")

    persist_dir: str = str(BACKEND_DIR / "memory" / "vector_db")
    collection_name: str = "bkai_knowledge"


class EmbeddingSettings(BaseSettings):
    """Embedding model configuration."""

    model_config = SettingsConfigDict(env_prefix="EMBEDDING_")

    model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    device: str = "cpu"
    batch_size: int = 64


class SearchSettings(BaseSettings):
    """Search & retrieval configuration."""

    hybrid_search_alpha: float = Field(default=0.7, ge=0.0, le=1.0)
    rerank_top_k: int = Field(default=5, ge=1, le=50)
    retrieval_top_k: int = Field(default=20, ge=1, le=100)

    model_config = SettingsConfigDict(env_prefix="")


class CacheSettings(BaseSettings):
    """Semantic cache configuration."""

    model_config = SettingsConfigDict(env_prefix="")

    semantic_cache_threshold: float = Field(default=0.92, ge=0.5, le=1.0)
    cache_ttl_unrated: int = 604800  # 7 days in seconds
    cache_ttl_liked: int = 2592000  # 30 days in seconds


class SecuritySettings(BaseSettings):
    """Security & rate limiting configuration."""

    model_config = SettingsConfigDict(env_prefix="")

    max_concurrent_users: int = 15
    rate_limit_per_minute: int = 30
    max_input_length: int = 500


class APISettings(BaseSettings):
    """FastAPI server configuration."""

    model_config = SettingsConfigDict(env_prefix="API_")

    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "http://localhost:5173,http://localhost:5174"
    debug: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        return [origin.strip() for origin in self.cors_origins.split(",")]


class WebSearchSettings(BaseSettings):
    """Web search tool configuration."""

    model_config = SettingsConfigDict(env_prefix="WEB_SEARCH_")

    domain: str = "hcmut.edu.vn"
    max_results: int = 5
    timeout: int = 15


class Settings(BaseSettings):
    """
    Master settings object aggregating all sub-configurations.

    Usage:
        from config.settings import get_settings
        settings = get_settings()
        print(settings.ollama.model_primary)
    """

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Sub-configurations
    ollama: OllamaSettings = Field(default_factory=OllamaSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    chroma: ChromaSettings = Field(default_factory=ChromaSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    search: SearchSettings = Field(default_factory=SearchSettings)
    cache: CacheSettings = Field(default_factory=CacheSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    api: APISettings = Field(default_factory=APISettings)
    web_search: WebSearchSettings = Field(default_factory=WebSearchSettings)

    # Path shortcuts
    @property
    def data_dir(self) -> Path:
        return DATA_DIR

    @property
    def raw_data_dir(self) -> Path:
        return RAW_DATA_DIR

    @property
    def csv_data_dir(self) -> Path:
        return CSV_DATA_DIR

    @property
    def processed_data_dir(self) -> Path:
        return PROCESSED_DATA_DIR


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Get cached singleton Settings instance.

    Returns a cached Settings object so that .env is only
    read once during application lifetime.
    """
    return Settings()
