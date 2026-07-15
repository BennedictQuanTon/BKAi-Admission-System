"""
BKAi API Routes.

REST endpoints for chat, feedback, stats, health, and voice interaction.
"""

from __future__ import annotations

import time
import os
import tempfile
import uuid

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse

from api.schemas import (
    ChatRequest, ChatResponse,
    FeedbackRequest, FeedbackResponse,
    StatsResponse, HealthResponse,
    VoiceTranscribeResponse, VoiceAskRequest, VoiceAskResponse,
    AdminEvaluateRequest, AdminDeleteRequest,
    ClearSessionRequest, ClearSessionResponse,
    LiveKitTokenRequest, LiveKitTokenResponse,
)
from memory.semantic_cache import (
    check_cache, store_in_cache,
    update_feedback, update_question_feedback,
    record_question, get_stats, record_error,
    evaluate_question_by_id, delete_question_by_id,
)
from api.dashboard_manager import stream_progress
from memory.conversation import get_conversation_memory
from workflows.main_graph import run_agent_pipeline
from utils.logger import get_logger
from utils.text_cleaning import sanitize_input

logger = get_logger(__name__)
router = APIRouter(prefix="/api")


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Main chat endpoint.

    1. Check semantic cache for similar liked answer.
    2. If cache miss, run the full agent pipeline.
    3. Store Q&A in cache and record stats.
    """
    t0 = time.time()
    query = sanitize_input(request.query)
    session_id = request.session_id
    channel = request.channel if request.channel in {"chat", "voice"} else "chat"
    query_id = f"q_{uuid.uuid4().hex[:8]}"
    memory = get_conversation_memory()
    history = memory.get_history(session_id)

    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    stream_progress(
        session_id=session_id,
        query_id=query_id,
        step="start",
        status="running",
        message=f"Received query: '{query[:60]}...'",
        query=query,
    )

    stream_progress(
        session_id=session_id,
        query_id=query_id,
        step="guardrail",
        status="running",
        message="Checking safety guardrails...",
    )

    from services.guardrails import GuardrailDecision, enforce_guardrails

    guard = await enforce_guardrails(query)
    if guard.decision == GuardrailDecision.REJECT:
        response_time = time.time() - t0
        stream_progress(
            session_id=session_id,
            query_id=query_id,
            step="guardrail",
            status="error",
            message=f"Guardrail check failed: {guard.rejection_message}",
        )
        stream_progress(
            session_id=session_id,
            query_id=query_id,
            step="complete",
            status="done",
            message=f"Processing terminated by guardrails in {response_time:.2f}s.",
            elapsed=round(response_time, 3),
        )
        memory.add_turn(session_id, "user", query)
        memory.add_turn(session_id, "assistant", guard.rejection_message)
        return ChatResponse(
            answer=guard.rejection_message,
            confidence=1.0,
            cached=False,
            session_id=session_id,
            timings={"total": round(response_time, 3), "guardrail": True},
            counselor_action="REJECT_SCOPE",
        )

    stream_progress(
        session_id=session_id,
        query_id=query_id,
        step="guardrail",
        status="done",
        message="Guardrail check passed.",
    )

    stream_progress(
        session_id=session_id,
        query_id=query_id,
        step="cache",
        status="running",
        message="Checking semantic cache for existing answers...",
    )

    # ── Step 1: Check semantic cache (skip during multi-turn) ──
    cached = None
    if not history:
        cached = check_cache(query)
    if cached:
        response_time = time.time() - t0
        stream_progress(
            session_id=session_id,
            query_id=query_id,
            step="cache",
            status="done",
            message=f"Cache hit! Found similar question with confidence {cached.get('confidence', 1.0)*100:.0f}%.",
        )
        stream_progress(
            session_id=session_id,
            query_id=query_id,
            step="complete",
            status="done",
            message=f"Query resolved using cache in {response_time:.2f}s.",
            elapsed=round(response_time, 3),
        )
        memory.add_turn(session_id, "user", query)
        memory.add_turn(session_id, "assistant", cached["answer"])
        record_question(
            query=query,
            answer=cached["answer"],
            response_time=response_time,
            build_time=0.0,
            cached=True,
            feedback="like",
            question_id=query_id,
        )
        return ChatResponse(
            answer=cached["answer"],
            confidence=cached.get("confidence", 1.0),
            cached=True,
            session_id=session_id,
            timings={"total": round(response_time, 3), "cache": True},
            counselor_action="CACHE",
        )

    stream_progress(
        session_id=session_id,
        query_id=query_id,
        step="cache",
        status="done",
        message="Cache miss. Invoking agent workflows...",
    )

    # ── Step 2: Run agent pipeline ──
    try:
        result = await run_agent_pipeline(
            query=query,
            session_id=session_id,
            query_id=query_id,
            channel=channel,
        )
    except Exception as e:
        logger.error("chat_pipeline_error", error=str(e))
        record_error("pipeline_error", str(e))
        stream_progress(
            session_id=session_id,
            query_id=query_id,
            step="complete",
            status="error",
            message=f"Agent workflow error: {str(e)}",
        )
        raise HTTPException(status_code=500, detail="Internal processing error")

    response_time = time.time() - t0
    build_time = result.get("timings", {}).get("total", response_time)

    stream_progress(
        session_id=session_id,
        query_id=query_id,
        step="complete",
        status="done",
        message=f"Query processed successfully in {response_time:.2f}s.",
        elapsed=round(response_time, 3),
    )

    # ── Step 3: Store in cache (only cold-start turns) and record stats ──
    if not history and result.get("counselor_action") != "ASK_CLARIFY":
        store_in_cache(
            query=query,
            answer=result["answer"],
            confidence=result.get("confidence", 0.0),
            timings=result.get("timings"),
            sources=result.get("sources"),
        )

    record_question(
        query=query,
        answer=result["answer"],
        response_time=response_time,
        build_time=build_time,
        cached=False,
        trace={
            "rewritten_queries": result.get("rewritten_queries", []),
            "sources": result.get("sources", []),
            "confidence": result.get("confidence", 0.0),
            "retrieval_hops": result.get("retrieval_hops", 0),
            "retrieval_decision": result.get("retrieval_decision", ""),
            "counselor_action": result.get("counselor_action", ""),
            "step_timings": result.get("timings", {}),
        },
        question_id=query_id,
    )

    return ChatResponse(
        answer=result["answer"],
        confidence=result.get("confidence", 0.0),
        sources=result.get("sources", []),
        cached=False,
        session_id=session_id,
        timings=result.get("timings", {}),
        retrieval_hops=result.get("retrieval_hops", 0),
        counselor_action=result.get("counselor_action", ""),
    )


@router.post("/session/clear", response_model=ClearSessionResponse)
async def clear_session(request: ClearSessionRequest) -> ClearSessionResponse:
    """Clear ephemeral chat memory + profile for a session (New chat)."""
    get_conversation_memory().clear_session(request.session_id)
    return ClearSessionResponse(status="ok", session_id=request.session_id)


@router.post("/livekit/token", response_model=LiveKitTokenResponse)
async def livekit_token(request: LiveKitTokenRequest) -> LiveKitTokenResponse:
    """Mint a LiveKit access token for the browser voice client."""
    from config.settings import get_settings

    settings = get_settings()
    if not settings.livekit.enabled:
        raise HTTPException(status_code=503, detail="LiveKit is not configured")

    try:
        from livekit import api as livekit_api
    except ImportError as e:
        raise HTTPException(status_code=503, detail="livekit package not installed") from e

    room_name = request.room_name or f"bkai-{request.session_id[:20]}"
    identity = f"user-{request.session_id[:16]}"
    token = (
        livekit_api.AccessToken(settings.livekit.api_key, settings.livekit.api_secret)
        .with_identity(identity)
        .with_name("BkAI User")
        .with_grants(
            livekit_api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
        .to_jwt()
    )
    return LiveKitTokenResponse(
        token=token,
        url=settings.livekit.url,
        room_name=room_name,
        session_id=request.session_id,
    )


@router.post("/feedback", response_model=FeedbackResponse)
async def feedback(request: FeedbackRequest) -> FeedbackResponse:
    """
    Record user feedback (like/dislike) for an answer.

    Liked answers are promoted in the semantic cache for reuse.
    """
    success = update_feedback(request.query, request.feedback)
    update_question_feedback(request.query, request.feedback)

    return FeedbackResponse(
        status="ok" if success else "not_found",
        cached=success,
    )


@router.post("/admin/evaluate")
async def admin_evaluate(request: AdminEvaluateRequest):
    """
    Evaluate a question response correctness from the admin dashboard.
    """
    success = evaluate_question_by_id(
        request.question_id,
        request.feedback,
        query=request.query,
        timestamp=request.timestamp,
    )
    if not success:
        raise HTTPException(status_code=404, detail="Question not found")
    return {"status": "ok"}


@router.post("/admin/delete")
async def admin_delete(request: AdminDeleteRequest):
    """
    Delete a question permanently from both stats and semantic cache.
    """
    success = delete_question_by_id(
        request.question_id,
        query=request.query,
        timestamp=request.timestamp,
    )
    if not success:
        raise HTTPException(status_code=404, detail="Question not found")
    return {"status": "ok"}


@router.get("/stats", response_model=StatsResponse)
async def stats() -> StatsResponse:
    """Get real-time stats for the monitoring dashboard."""
    data = get_stats()
    memory = get_conversation_memory()
    data["active_sessions"] = memory.active_sessions()
    return StatsResponse(**data)


@router.get("/stats/history")
async def stats_history(hours: int = 24):
    """Get stats snapshots for trend charts."""
    from memory.semantic_cache import get_stats_history
    return {"history": get_stats_history(hours)}


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse()


# ──────────────────────────────────────────────
# Voice Interaction Endpoints
# ──────────────────────────────────────────────
# Temp directory for voice audio files
VOICE_AUDIO_DIR = tempfile.mkdtemp(prefix="bkai_voice_")


@router.post("/voice/transcribe", response_model=VoiceTranscribeResponse)
async def voice_transcribe(
    audio: UploadFile = File(..., description="Audio file from browser recorder"),
):
    """
    Voice transcription endpoint (STT only).

    Accepts an audio file recorded from the browser, runs it through
    faster-whisper for Vietnamese transcription, and returns the text.

    This endpoint is intentionally separated from the RAG pipeline
    to provide instant visual feedback to the user.
    """
    from services.audio_service import speech_to_text

    # Save uploaded audio to temp file
    suffix = ".webm" if "webm" in (audio.content_type or "") else ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=VOICE_AUDIO_DIR) as tmp:
        content = await audio.read()
        tmp.write(content)
        temp_path = tmp.name

    try:
        result = await speech_to_text(temp_path)

        if not result["text"]:
            raise HTTPException(
                status_code=400,
                detail="Không thể nhận diện giọng nói. Vui lòng thử lại.",
            )

        return VoiceTranscribeResponse(
            text=result["text"],
            language=result.get("language", "vi"),
            duration=result.get("duration", 0.0),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("voice_transcribe_error", error=str(e))
        raise HTTPException(status_code=500, detail="Lỗi xử lý giọng nói")
    finally:
        # Cleanup input file
        try:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        except OSError:
            pass


@router.post("/voice/ask")
async def voice_ask(
    request: VoiceAskRequest,
    background_tasks: BackgroundTasks,
):
    """
    Voice ask endpoint (Text → RAG Pipeline → TTS → Audio).

    Takes transcribed text, runs it through the full RAG pipeline,
    generates TTS audio of the answer, and returns both the text
    answer and a downloadable audio file.

    The response includes the audio file with metadata headers.
    """
    from services.audio_service import text_to_speech

    t0 = time.time()
    query = sanitize_input(request.text)
    session_id = request.session_id
    channel = "voice"
    query_id = f"q_{uuid.uuid4().hex[:8]}"
    memory = get_conversation_memory()
    history = memory.get_history(session_id)

    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    stream_progress(
        session_id=session_id,
        query_id=query_id,
        step="start",
        status="running",
        message=f"Received voice query: '{query[:60]}...'",
        query=query,
    )

    stream_progress(
        session_id=session_id,
        query_id=query_id,
        step="guardrail",
        status="running",
        message="Checking safety guardrails...",
    )

    from services.guardrails import GuardrailDecision, enforce_guardrails

    guard = await enforce_guardrails(query)
    if guard.decision == GuardrailDecision.REJECT:
        response_time = time.time() - t0
        stream_progress(
            session_id=session_id,
            query_id=query_id,
            step="guardrail",
            status="error",
            message=f"Guardrail check failed: {guard.rejection_message}",
        )
        stream_progress(
            session_id=session_id,
            query_id=query_id,
            step="complete",
            status="done",
            message=f"Processing terminated by guardrails in {response_time:.2f}s.",
            elapsed=round(response_time, 3),
        )
        memory.add_turn(session_id, "user", query)
        memory.add_turn(session_id, "assistant", guard.rejection_message)
        return JSONResponse(content={
            "answer": guard.rejection_message,
            "audio_url": "",
            "confidence": 1.0,
            "cached": False,
            "session_id": session_id,
            "timings": {"total": round(response_time, 3), "guardrail": True},
        })

    stream_progress(
        session_id=session_id,
        query_id=query_id,
        step="guardrail",
        status="done",
        message="Guardrail check passed.",
    )

    stream_progress(
        session_id=session_id,
        query_id=query_id,
        step="cache",
        status="running",
        message="Checking semantic cache for existing answers...",
    )

    # ── Step 1: Check semantic cache (skip multi-turn) ──
    cached_result = check_cache(query) if not history else None

    if cached_result:
        ai_answer = cached_result["answer"]
        response_time = time.time() - t0
        stream_progress(
            session_id=session_id,
            query_id=query_id,
            step="cache",
            status="done",
            message=f"Cache hit! Found similar question with confidence {cached_result.get('confidence', 1.0)*100:.0f}%.",
        )
        stream_progress(
            session_id=session_id,
            query_id=query_id,
            step="complete",
            status="done",
            message=f"Query resolved using cache in {response_time:.2f}s.",
            elapsed=round(response_time, 3),
        )
        memory.add_turn(session_id, "user", query)
        memory.add_turn(session_id, "assistant", ai_answer)
        record_question(
            query=query,
            answer=ai_answer,
            response_time=response_time,
            build_time=0.0,
            cached=True,
            feedback="like",
            question_id=query_id,
        )
        confidence = cached_result.get("confidence", 1.0)
        is_cached = True
        timings = {"total": round(response_time, 3)}
    else:
        stream_progress(
            session_id=session_id,
            query_id=query_id,
            step="cache",
            status="done",
            message="Cache miss. Invoking agent workflows...",
        )
        # ── Step 2: Run counselor + Agentic RAG pipeline ──
        try:
            result = await run_agent_pipeline(
                query=query,
                session_id=session_id,
                query_id=query_id,
                channel=channel,
            )
        except Exception as e:
            logger.error("voice_pipeline_error", error=str(e))
            stream_progress(
                session_id=session_id,
                query_id=query_id,
                step="complete",
                status="error",
                message=f"Agent workflow error: {str(e)}",
            )
            raise HTTPException(status_code=500, detail="Lỗi xử lý câu hỏi")

        ai_answer = result["answer"]
        response_time = time.time() - t0
        build_time = result.get("timings", {}).get("total", response_time)
        confidence = result.get("confidence", 0.0)
        is_cached = False
        timings = result.get("timings", {})

        stream_progress(
            session_id=session_id,
            query_id=query_id,
            step="complete",
            status="done",
            message=f"Query processed successfully in {response_time:.2f}s.",
            elapsed=round(response_time, 3),
        )

        if not history and result.get("counselor_action") != "ASK_CLARIFY":
            store_in_cache(
                query=query,
                answer=ai_answer,
                confidence=confidence,
                timings=timings,
                sources=result.get("sources"),
            )
        record_question(
            query=query,
            answer=ai_answer,
            response_time=response_time,
            build_time=build_time,
            cached=False,
            question_id=query_id,
        )

    # ── Step 3: Generate TTS audio ──
    audio_filename = f"voice_{uuid.uuid4().hex[:12]}.mp3"
    audio_path = os.path.join(VOICE_AUDIO_DIR, audio_filename)

    try:
        await text_to_speech(ai_answer, audio_path)
    except Exception as e:
        logger.error("voice_tts_error", error=str(e))
        # Return text-only response if TTS fails
        return JSONResponse(content={
            "answer": ai_answer,
            "audio_url": "",
            "confidence": confidence,
            "cached": is_cached,
            "session_id": session_id,
            "timings": timings,
            "tts_error": str(e),
        })

    # Schedule cleanup of audio file after response
    def cleanup_audio():
        try:
            if os.path.exists(audio_path):
                os.unlink(audio_path)
        except OSError as e:
            logger.warning("voice_cleanup_error", error=str(e))

    background_tasks.add_task(cleanup_audio)

    # Return audio file with metadata in headers
    import urllib.parse
    headers = {
        "X-Answer-Text": urllib.parse.quote(ai_answer[:2000].encode("utf-8")),
        "X-Confidence": str(round(confidence, 4)),
        "X-Cached": str(is_cached).lower(),
        "X-Session-Id": session_id,
        "X-Response-Time": str(round(response_time, 3)),
        "Access-Control-Expose-Headers": (
            "X-Answer-Text, X-Confidence, X-Cached, X-Session-Id, X-Response-Time"
        ),
    }

    return FileResponse(
        path=audio_path,
        media_type="audio/mpeg",
        headers=headers,
        filename="bkai_response.mp3",
    )

