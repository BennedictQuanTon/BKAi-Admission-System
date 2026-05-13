"""
BKAi Self-Reflection Agent.

Validates generated answers for factual accuracy, completeness,
and hallucination before returning to the user.
"""

from __future__ import annotations

import json
import time

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_ollama import ChatOllama

from agents.state import AgentState
from config.settings import get_settings
from config.prompts import SELF_REFLECTION_PROMPT
from utils.logger import AgentTracer

tracer = AgentTracer("self_reflection")

CONFIDENCE_THRESHOLD = 0.7


def self_reflect_node(state: AgentState) -> dict:
    """
    LangGraph node: Evaluate answer quality before returning.

    Uses the primary model (qwen2.5:7b) for thorough quality assessment.
    Returns confidence score and issues list.
    """
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

    settings = get_settings()

    try:
        llm = ChatOllama(
            model=settings.ollama.model_primary,
            base_url=settings.ollama.base_url,
            temperature=0.0,
            num_ctx=settings.ollama.num_ctx,
        )

        messages = [
            SystemMessage(content=SELF_REFLECTION_PROMPT),
            HumanMessage(content=(
                f"## Câu hỏi\n{query}\n\n"
                f"## Context đã cung cấp\n{context[:2000]}\n\n"
                f"## Câu trả lời cần đánh giá\n{answer}"
            )),
        ]

        response = llm.invoke(messages)
        result = _parse_reflection(response.content.strip())

    except Exception as e:
        tracer.error("self_reflect", error=str(e))
        result = {
            "confidence": 0.8,  # Default pass on error
            "is_acceptable": True,
            "issues": [],
        }

    elapsed = time.time() - t0
    tracer.end(
        "self_reflect",
        confidence=result["confidence"],
        acceptable=result["is_acceptable"],
        elapsed=round(elapsed, 2),
    )

    return {
        "answer_confidence": result["confidence"],
        "answer_issues": result.get("issues", []),
        "current_step": "self_reflect",
        "step_timings": {
            **state.get("step_timings", {}),
            "self_reflect": round(elapsed, 3),
        },
    }


def should_retry(state: AgentState) -> str:
    """
    LangGraph conditional edge: decide next step after self-reflection.

    Returns:
        "retry" if confidence is too low and we haven't exceeded retries.
        "accept" if answer is acceptable.
    """
    confidence = state.get("answer_confidence", 1.0)
    iterations = state.get("iteration_count", 0)

    if confidence < CONFIDENCE_THRESHOLD and iterations < 2:
        return "retry"
    return "accept"


def _parse_reflection(content: str) -> dict:
    """Parse self-reflection LLM response."""
    try:
        json_start = content.find("{")
        json_end = content.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            data = json.loads(content[json_start:json_end])
            return {
                "confidence": float(data.get("confidence", 0.8)),
                "is_acceptable": bool(data.get("is_acceptable", True)),
                "issues": list(data.get("issues", [])),
            }
    except (json.JSONDecodeError, KeyError, ValueError):
        pass

    # Fallback: assume acceptable
    return {"confidence": 0.8, "is_acceptable": True, "issues": []}
