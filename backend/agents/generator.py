"""
BkAI Answer Generator — counselor-aware, chat vs voice channels.
"""

from __future__ import annotations

import time

from langchain_core.messages import HumanMessage

from agents.state import AgentState
from config.prompts import (
    ANSWER_GENERATION_PROMPT,
    ANSWER_GENERATION_VOICE_PROMPT,
    COUNSELOR_PERSONA,
    MODE_ADVISE,
    MODE_CLARIFY,
    MODE_RETRIEVE,
)
from services.llm_factory import acquire_rpm_slot, get_primary_llm
from services.stream_context import emit_token
from utils.logger import AgentTracer

from api.dashboard_manager import stream_progress

tracer = AgentTracer("generator")


async def generate_answer_node(state: AgentState) -> dict:
    t0 = time.time()
    session_id = state.get("session_id", "")
    query_id = state.get("query_id", "")
    channel = state.get("channel", "chat")
    action = (state.get("counselor_action") or "RETRIEVE").upper()

    stream_progress(
        session_id=session_id,
        query_id=query_id,
        step="generate",
        status="running",
        message="Counselor generating answer...",
    )
    tracer.start("generate", channel=channel, action=action)

    query = state.get("resolved_query") or state["original_query"]
    context = state.get("retrieval_context", "Không có dữ liệu liên quan.")
    history = state.get("chat_history", [])
    profile = state.get("student_profile", {})

    if action == "ASK_CLARIFY":
        clarify = state.get("clarify_question") or (
            "Bạn cho mình biết thêm điểm số (hoặc ĐGNL) và ngành bạn đang quan tâm được không?"
        )
        if channel == "voice":
            answer = clarify
        else:
            answer = (
                f"{clarify}\n\n"
                "_Mình cần thêm thông tin này để tư vấn sát hơn — không bắt buộc nếu bạn chưa muốn chia sẻ._"
            )
        elapsed = time.time() - t0
        stream_progress(
            session_id=session_id,
            query_id=query_id,
            step="generate",
            status="done",
            message=f"Clarify question returned ({elapsed:.2f}s).",
            elapsed=round(elapsed, 3),
        )
        return {
            "generated_answer": answer,
            "current_step": "generate",
            "iteration_count": state.get("iteration_count", 0) + 1,
            "step_timings": {
                **state.get("step_timings", {}),
                "generate": round(elapsed, 3),
            },
        }

    history_str = ""
    if history:
        parts = []
        for turn in history[-6:]:
            role = "Người dùng" if turn.get("role") == "user" else "BkAI"
            parts.append(f"{role}: {turn.get('content', '')}")
        history_str = "\n".join(parts)

    profile_str = "chưa có"
    if isinstance(profile, dict) and profile:
        from memory.student_profile import StudentProfile

        profile_str = StudentProfile.model_validate(profile).summary_vi()

    mode_instruction = MODE_ADVISE if action == "ADVISE" else MODE_RETRIEVE
    template = ANSWER_GENERATION_VOICE_PROMPT if channel == "voice" else ANSWER_GENERATION_PROMPT
    prompt = template.format(
        persona=COUNSELOR_PERSONA,
        context=context,
        profile=profile_str,
        chat_history=history_str or "Không có lịch sử hội thoại.",
        question=query,
        mode_instruction=mode_instruction,
    )

    answer = ""
    try:
        await acquire_rpm_slot("primary")
        llm = get_primary_llm()
        messages = [HumanMessage(content=prompt)]

        chunks: list[str] = []
        async for chunk in llm.astream(messages):
            text = chunk.content if hasattr(chunk, "content") else str(chunk)
            if isinstance(text, list):
                text = "".join(
                    block.get("text", "") if isinstance(block, dict) else str(block)
                    for block in text
                )
            if text:
                chunks.append(text)
                await emit_token(text)

        answer = "".join(chunks).strip()
        if not answer:
            response = await llm.ainvoke(messages)
            answer = response.content.strip()

    except Exception as e:
        tracer.error("generate", error=str(e))
        answer = (
            "Xin lỗi, mình gặp sự cố khi xử lý câu hỏi của bạn. "
            "Bạn thử lại giúp mình nhé."
        )

    elapsed = time.time() - t0
    tracer.end("generate", answer_len=len(answer), elapsed=round(elapsed, 2))

    stream_progress(
        session_id=session_id,
        query_id=query_id,
        step="generate",
        status="done",
        message=f"Answer generation completed in {elapsed:.2f}s.",
        elapsed=round(elapsed, 3),
    )

    return {
        "generated_answer": answer,
        "current_step": "generate",
        "iteration_count": state.get("iteration_count", 0) + 1,
        "step_timings": {
            **state.get("step_timings", {}),
            "generate": round(elapsed, 3),
        },
    }
