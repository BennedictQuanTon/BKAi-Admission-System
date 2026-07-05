"""
BkAI LLM Factory — dual-model Gemini routing with per-model RPM limiting.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Literal

from langchain_google_genai import ChatGoogleGenerativeAI

from config.settings import get_settings
from utils.logger import get_logger

logger = get_logger(__name__)

ModelTier = Literal["fast", "primary"]

_fast_llm: ChatGoogleGenerativeAI | None = None
_primary_llm: ChatGoogleGenerativeAI | None = None

_lite_timestamps: deque[float] = deque()
_flash_timestamps: deque[float] = deque()
_rpm_lock = asyncio.Lock()


class GeminiRateLimitError(Exception):
    """Raised when Gemini RPM quota is exhausted."""

    def __init__(self, tier: ModelTier, retry_after: float):
        self.tier = tier
        self.retry_after = retry_after
        super().__init__(f"Gemini {tier} RPM limit reached. Retry after {retry_after:.1f}s")


async def acquire_rpm_slot(tier: ModelTier) -> None:
    """Block until an RPM slot is available for the given model tier."""
    settings = get_settings()
    limit = (
        settings.gemini.rpm_limit_lite
        if tier == "fast"
        else settings.gemini.rpm_limit_flash
    )
    timestamps = _lite_timestamps if tier == "fast" else _flash_timestamps

    async with _rpm_lock:
        now = time.monotonic()
        while timestamps and now - timestamps[0] >= 60.0:
            timestamps.popleft()

        if len(timestamps) >= limit:
            retry_after = 60.0 - (now - timestamps[0]) + 0.1
            raise GeminiRateLimitError(tier, retry_after)

        timestamps.append(now)


def get_fast_llm() -> ChatGoogleGenerativeAI:
    global _fast_llm
    if _fast_llm is None:
        settings = get_settings()
        _fast_llm = ChatGoogleGenerativeAI(
            model=settings.gemini.model_fast,
            google_api_key=settings.google.api_key,
            temperature=settings.gemini.temperature_fast,
            timeout=settings.gemini.request_timeout,
        )
        logger.info("gemini_fast_initialized", model=settings.gemini.model_fast)
    return _fast_llm


def get_primary_llm() -> ChatGoogleGenerativeAI:
    global _primary_llm
    if _primary_llm is None:
        settings = get_settings()
        _primary_llm = ChatGoogleGenerativeAI(
            model=settings.gemini.model_primary,
            google_api_key=settings.google.api_key,
            temperature=settings.gemini.temperature_primary,
            timeout=settings.gemini.request_timeout,
        )
        logger.info("gemini_primary_initialized", model=settings.gemini.model_primary)
    return _primary_llm


def get_llm(tier: ModelTier) -> ChatGoogleGenerativeAI:
    return get_fast_llm() if tier == "fast" else get_primary_llm()
