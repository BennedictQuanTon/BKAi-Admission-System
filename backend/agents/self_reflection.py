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

tracer = AgentTracer("self_reflection")
CONFIDENCE_THRESHOLD = 0.7


class ReflectionOutput(BaseModel):
    confidence: float = Field(ge=0.0, le=1.0)
    is_acceptable: bool = True
    issues: list[str] = Field(default_factory=list)


async def self_reflect_node(state: AgentState) -> dict:
    t0 = time.time()
    tracer.start("self_reflect")

    answer = state.get("generated_answer", "")
    context = state.get("retrieval_context", "")
    query = state["original_query"]

    if not answer:
        return {
            "answer_confidence": 0.0,
            "answer_issues": ["Empty answer generated"],
            "current_step": "self_reflect",
        }

    if not query_has_numeric_facts(query):
        elapsed = time.time() - t0
        tracer.end("self_reflect", confidence=0.85, acceptable=True, skipped=True)
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
    confidence = state.get("answer_confidence", 1.0)
    iterations = state.get("iteration_count", 0)

    if confidence < CONFIDENCE_THRESHOLD and iterations < 2:
        return "retry"
    return "accept"
