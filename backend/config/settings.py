"""
BkAI Backend Configuration Module.

Centralized settings management using Pydantic BaseSettings.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
DATA_DIR = BACKEND_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
CSV_DATA_DIR = DATA_DIR / "csv"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
ENV_FILE = str(BACKEND_DIR / ".env")


class GeminiSettings(BaseSettings):
    """Google Gemini API configuration."""

    model_config = SettingsConfigDict(env_prefix="GEMINI_")

    model_primary: str = "gemini-2.5-flash-lite"
    model_fast: str = "gemini-2.5-flash-lite"
    rpm_limit_lite: int = 10
    rpm_limit_flash: int = 10
    request_timeout: int = 120
    temperature_primary: float = 0.3
    temperature_fast: float = 0.2


class GoogleSettings(BaseSettings):
    """Google API key."""

    model_config = SettingsConfigDict(env_prefix="GOOGLE_")

    api_key: str = ""


class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REDIS_")

    url: str = "redis://localhost:6379/0"
    cache_db: int = 1
    stats_db: int = 2
    max_connections: int = 20


class ChromaSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CHROMA_")

    persist_dir: str = str(BACKEND_DIR / "memory" / "vector_db")
    collection_name: str = "bkai_knowledge"



class EmbeddingSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EMBEDDING_")

    model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    device: str = "cpu"
    batch_size: int = 32


class SearchSettings(BaseSettings):
    hybrid_search_alpha: float = Field(default=0.7, ge=0.0, le=1.0)
    rerank_top_k: int = Field(default=8, ge=1, le=50)
    retrieval_top_k: int = Field(default=20, ge=1, le=100)

    model_config = SettingsConfigDict(env_prefix="")


class CacheSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="")

    semantic_cache_threshold: float = Field(default=0.92, ge=0.5, le=1.0)
    cache_ttl_unrated: int = 604800
    cache_ttl_liked: int = 2592000


class SecuritySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="")

    max_concurrent_users: int = 8
    rate_limit_per_minute: int = 15
    max_input_length: int = 500


class GuardrailsSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GUARDRAILS_")

    enabled: bool = True
    allowed_scope: str = "HCMUT_ADMISSIONS"


class MCPSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MCP_")

    scraper_enabled: bool = True
    scraper_allowed_domains: str = "hcmut.edu.vn,www.hcmut.edu.vn"
    max_pages: int = 2
    timeout: int = 10

    @property
    def allowed_domain_list(self) -> list[str]:
        return [d.strip() for d in self.scraper_allowed_domains.split(",") if d.strip()]


class APISettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="API_")

    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "http://localhost:5173,http://localhost:5174,http://localhost:5175"
    debug: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]


class WebSearchSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WEB_SEARCH_")

    domain: str = "hcmut.edu.vn"
    max_results: int = 5
    timeout: int = 15


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_")

    name: str = "BkAI"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    google: GoogleSettings = Field(default_factory=GoogleSettings)
    gemini: GeminiSettings = Field(default_factory=GeminiSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    chroma: ChromaSettings = Field(default_factory=ChromaSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    search: SearchSettings = Field(default_factory=SearchSettings)
    cache: CacheSettings = Field(default_factory=CacheSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    guardrails: GuardrailsSettings = Field(default_factory=GuardrailsSettings)
    mcp: MCPSettings = Field(default_factory=MCPSettings)
    api: APISettings = Field(default_factory=APISettings)
    web_search: WebSearchSettings = Field(default_factory=WebSearchSettings)
    app: AppSettings = Field(default_factory=AppSettings)

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
    from dotenv import load_dotenv

    load_dotenv(ENV_FILE, override=False)
    return Settings()
