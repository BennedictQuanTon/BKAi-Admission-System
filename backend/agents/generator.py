"""
BKAi Answer Generator.

Generates the final answer using retrieved context and the primary LLM.
"""

from __future__ import annotations

import time

from langchain_core.messages import HumanMessage
from langchain_ollama import ChatOllama

from agents.state import AgentState
from config.settings import get_settings
from config.prompts import ANSWER_GENERATION_PROMPT
from utils.logger import AgentTracer

tracer = AgentTracer("generator")


def generate_answer_node(state: AgentState) -> dict:
    """
    LangGraph node: Generate the final answer using retrieved context.

    Uses the primary model (qwen2.5:7b) for highest quality Vietnamese output.
    """
    t0 = time.time()
    tracer.start("generate")

    query = state["original_query"]
    context = state.get("retrieval_context", "Không có dữ liệu liên quan.")
    history = state.get("chat_history", [])

    settings = get_settings()

    # Format chat history
    history_str = ""
    if history:
        parts = []
        for turn in history[-6:]:  # Last 3 exchanges
            role = "Người dùng" if turn.get("role") == "user" else "BKAi"
            parts.append(f"{role}: {turn.get('content', '')}")
        history_str = "\n".join(parts)

    # Build the prompt
    prompt = ANSWER_GENERATION_PROMPT.format(
        context=context,
        chat_history=history_str or "Không có lịch sử hội thoại.",
        question=query,
    )

    try:
        llm = ChatOllama(
            model=settings.ollama.model_primary,
            base_url=settings.ollama.base_url,
            temperature=0.3,
            num_ctx=settings.ollama.num_ctx,
        )

        messages = [HumanMessage(content=prompt)]
        response = llm.invoke(messages)
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
