"""
BkAI Answer Generator — Gemini Flash with token streaming.
"""

from __future__ import annotations

import time

from langchain_core.messages import HumanMessage

from agents.state import AgentState
from config.prompts import ANSWER_GENERATION_PROMPT
from services.llm_factory import acquire_rpm_slot, get_primary_llm
from services.stream_context import emit_token
from utils.logger import AgentTracer

tracer = AgentTracer("generator")


async def generate_answer_node(state: AgentState) -> dict:
    t0 = time.time()
    tracer.start("generate")

    query = state["original_query"]
    context = state.get("retrieval_context", "Không có dữ liệu liên quan.")
    history = state.get("chat_history", [])

    history_str = ""
    if history:
        parts = []
        for turn in history[-6:]:
            role = "Người dùng" if turn.get("role") == "user" else "BkAI"
            parts.append(f"{role}: {turn.get('content', '')}")
        history_str = "\n".join(parts)

    prompt = ANSWER_GENERATION_PROMPT.format(
        context=context,
        chat_history=history_str or "Không có lịch sử hội thoại.",
        question=query,
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
            "Xin lỗi, tôi gặp sự cố khi xử lý câu hỏi của bạn. "
            "Vui lòng thử lại sau."
        )

    elapsed = time.time() - t0
    tracer.end("generate", answer_len=len(answer), elapsed=round(elapsed, 2))

    return {
        "generated_answer": answer,
        "current_step": "generate",
        "iteration_count": state.get("iteration_count", 0) + 1,
        "step_timings": {
            **state.get("step_timings", {}),
            "generate": round(elapsed, 3),
        },
    }
