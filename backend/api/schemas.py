"""
BKAi API Schemas.

Pydantic models for request/response validation.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Chat endpoint request."""
    query: str = Field(..., min_length=1, max_length=500, description="User question")
    session_id: str = Field(default="default", max_length=64)


class ChatResponse(BaseModel):
    """Chat endpoint response."""
    answer: str
    confidence: float = 0.0
    sources: list[str] = []
    cached: bool = False
    session_id: str = ""
    timings: dict[str, float] = {}
    retrieval_hops: int = 0


class FeedbackRequest(BaseModel):
    """Feedback (like/dislike) request."""
    query: str = Field(..., min_length=1)
    answer: str = Field(..., min_length=1)
    feedback: str = Field(..., pattern="^(like|dislike)$")
    session_id: str = "default"


class FeedbackResponse(BaseModel):
    """Feedback response."""
    status: str = "ok"
    cached: bool = False


class StatsResponse(BaseModel):
    """Dashboard stats response."""
    total_questions: int = 0
    liked: int = 0
    disliked: int = 0
    unrated: int = 0
    avg_response_time: float = 0.0
    avg_build_time: float = 0.0
    cache_hit_rate: float = 0.0
    active_sessions: int = 0
    recent_questions: list[dict] = []


class VoiceTranscribeResponse(BaseModel):
    """Voice transcription (STT) response."""
    text: str
    language: str = "vi"
    duration: float = 0.0


class VoiceAskRequest(BaseModel):
    """Voice ask endpoint request (text from STT → RAG → TTS)."""
    text: str = Field(..., min_length=1, max_length=500, description="Transcribed user question")
    session_id: str = Field(default="voice_default", max_length=64)


class VoiceAskResponse(BaseModel):
    """Voice ask endpoint response."""
    answer: str
    audio_url: str = ""
    confidence: float = 0.0
    cached: bool = False
    session_id: str = ""
    timings: dict[str, float] = {}


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "healthy"
    service: str = "BKAi"
    version: str = "1.0.0"
