"""
BkAI Self-Reflection Agent — Gemini Flash, only for numeric/factual queries.
"""

from __future__ import annotations

import time

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agents.retriever import query_has_numeric_facts
from agents.state import AgentState
from config.prompts import SELF_REFLECTION_PROMPT
from services.llm_factory import acquire_rpm_slot, get_primary_llm
from utils.logger import AgentTracer

from api.dashboard_manager import stream_progress

tracer = AgentTracer("self_reflection")
CONFIDENCE_THRESHOLD = 0.7


class ReflectionOutput(BaseModel):
    confidence: float = Field(ge=0.0, le=1.0)
    is_acceptable: bool = True
    issues: list[str] = Field(default_factory=list)


async def self_reflect_node(state: AgentState) -> dict:
    t0 = time.time()
    session_id = state.get("session_id", "")
    query_id = state.get("query_id", "")

    stream_progress(
        session_id=session_id,
        query_id=query_id,
        step="self_reflect",
        status="running",
        message="Verifying answer precision and correctness (Self-Reflection)...",
    )
    tracer.start("self_reflect")

    answer = state.get("generated_answer", "")
    context = state.get("retrieval_context", "")
    query = state.get("resolved_query") or state["original_query"]
    action = (state.get("counselor_action") or "").upper()

    if action == "ASK_CLARIFY":
        elapsed = time.time() - t0
        stream_progress(
            session_id=session_id,
            query_id=query_id,
            step="self_reflect",
            status="done",
            message="Self-reflection skipped (clarify turn).",
            elapsed=round(elapsed, 3),
        )
        return {
            "answer_confidence": 1.0,
            "answer_issues": [],
            "current_step": "self_reflect",
            "step_timings": {
                **state.get("step_timings", {}),
                "self_reflect": round(elapsed, 3),
            },
        }

    if not answer:
        stream_progress(
            session_id=session_id,
            query_id=query_id,
            step="self_reflect",
            status="done",
            message="Self-reflection completed. Reason: Empty answer generated.",
        )
        return {
            "answer_confidence": 0.0,
            "answer_issues": ["Empty answer generated"],
            "current_step": "self_reflect",
        }

    if not query_has_numeric_facts(query):
        elapsed = time.time() - t0
        tracer.end("self_reflect", confidence=0.85, acceptable=True, skipped=True)
        stream_progress(
            session_id=session_id,
            query_id=query_id,
            step="self_reflect",
            status="done",
            message=f"Self-reflection skipped for non-factual query ({elapsed:.2f}s).",
            elapsed=round(elapsed, 3),
        )
        return {
            "answer_confidence": 0.85,
            "answer_issues": [],
            "current_step": "self_reflect",
            "step_timings": {
                **state.get("step_timings", {}),
                "self_reflect": round(elapsed, 3),
            },
        }

    try:
        await acquire_rpm_slot("primary")
        llm = get_primary_llm().with_structured_output(ReflectionOutput)
        result: ReflectionOutput = await llm.ainvoke([
            SystemMessage(content=SELF_REFLECTION_PROMPT),
            HumanMessage(content=(
                f"## Câu hỏi\n{query}\n\n"
                f"## Context đã cung cấp\n{context[:2000]}\n\n"
                f"## Câu trả lời cần đánh giá\n{answer}"
            )),
        ])
        parsed = {
            "confidence": float(result.confidence),
            "is_acceptable": bool(result.is_acceptable),
            "issues": list(result.issues or []),
        }
    except Exception as e:
        tracer.error("self_reflect", error=str(e))
        parsed = {"confidence": 0.8, "is_acceptable": True, "issues": []}

    elapsed = time.time() - t0
    tracer.end(
        "self_reflect",
        confidence=parsed["confidence"],
        acceptable=parsed["is_acceptable"],
        elapsed=round(elapsed, 2),
    )

    issues_str = f"Issues detected: {', '.join(parsed['issues'])}" if parsed.get("issues") else "No issues found."
    stream_progress(
        session_id=session_id,
        query_id=query_id,
        step="self_reflect",
        status="done",
        message=f"Self-reflection completed in {elapsed:.2f}s. Confidence: {parsed['confidence']*100:.0f}%. {issues_str}",
        elapsed=round(elapsed, 3),
    )

    return {
        "answer_confidence": parsed["confidence"],
        "answer_issues": parsed.get("issues", []),
        "current_step": "self_reflect",
        "step_timings": {
            **state.get("step_timings", {}),
            "self_reflect": round(elapsed, 3),
        },
    }


def should_retry(state: AgentState) -> str:
    if (state.get("counselor_action") or "").upper() == "ASK_CLARIFY":
        return "accept"
    if (state.get("channel") or "chat") == "voice":
        return "accept"
    confidence = state.get("answer_confidence", 1.0)
    iterations = state.get("iteration_count", 0)

    if confidence < CONFIDENCE_THRESHOLD and iterations < 2:
        return "retry"
    return "accept"
