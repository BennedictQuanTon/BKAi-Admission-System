"""
BkAI Query Rewriting + context resolve + counselor policy (single Gemini call).
"""

from __future__ import annotations

import time

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agents.state import AgentState
from config.prompts import QUERY_REWRITER_PROMPT
from memory.conversation import get_conversation_memory
from services.llm_factory import acquire_rpm_slot, get_fast_llm
from utils.logger import AgentTracer

from api.dashboard_manager import stream_progress

tracer = AgentTracer("query_rewriter")


class ProfilePatch(BaseModel):
    score_thpt: float | None = None
    score_dgnl: float | None = None
    subject_combo: str | None = None
    preferred_majors: list[str] = Field(default_factory=list)
    preferred_program: str | None = None
    budget_note: str | None = None
    admission_method: str | None = None
    notes: str | None = None


class RewriteOutput(BaseModel):
    resolved_query: str = ""
    rewritten_queries: list[str] = Field(default_factory=list)
    hyde_document: str = ""
    action: str = "RETRIEVE"
    clarify_question: str = ""
    profile_patch: ProfilePatch = Field(default_factory=ProfilePatch)


def _format_history(history: list[dict[str, str]], limit: int = 8) -> str:
    if not history:
        return "Không có lịch sử."
    parts = []
    for turn in history[-limit:]:
        role = "Người dùng" if turn.get("role") == "user" else "BkAI"
        parts.append(f"{role}: {turn.get('content', '')}")
    return "\n".join(parts)


async def query_rewrite_node(state: AgentState) -> dict:
    t0 = time.time()
    query = state["original_query"]
    session_id = state.get("session_id", "")
    query_id = state.get("query_id", "")
    history = state.get("chat_history", [])
    profile = state.get("student_profile", {})

    stream_progress(
        session_id=session_id,
        query_id=query_id,
        step="query_rewrite",
        status="running",
        message="Resolving context & optimizing query...",
        query=query,
    )
    tracer.start("rewrite", query=query[:80])

    try:
        await acquire_rpm_slot("fast")
        llm = get_fast_llm().with_structured_output(RewriteOutput)
        result: RewriteOutput = await llm.ainvoke([
            SystemMessage(content=QUERY_REWRITER_PROMPT),
            HumanMessage(content=(
                f"## Hồ sơ tạm\n{profile or 'chưa có'}\n\n"
                f"## Lịch sử\n{_format_history(history)}\n\n"
                f"## Câu hỏi mới\n{query}"
            )),
        ])
        resolved = (result.resolved_query or query).strip()
        queries = list(result.rewritten_queries or [])
        if resolved not in queries:
            queries.insert(0, resolved)
        if query not in queries:
            queries.append(query)
        action = (result.action or "RETRIEVE").upper().strip()
        if action not in {"ASK_CLARIFY", "RETRIEVE", "ADVISE"}:
            action = "RETRIEVE"
        patch = result.profile_patch.model_dump() if result.profile_patch else {}
        if session_id and patch:
            get_conversation_memory().update_profile(session_id, patch)
            profile = get_conversation_memory().get_profile(session_id).model_dump()
        rewritten = {
            "resolved_query": resolved,
            "rewritten_queries": queries[:3],
            "hyde_document": result.hyde_document or "",
            "counselor_action": action,
            "clarify_question": result.clarify_question or "",
            "profile_patch": patch,
            "student_profile": profile,
        }
    except Exception as e:
        tracer.error("rewrite", error=str(e))
        rewritten = {
            "resolved_query": query,
            "rewritten_queries": [query],
            "hyde_document": "",
            "counselor_action": "RETRIEVE",
            "clarify_question": "",
            "profile_patch": {},
            "student_profile": profile,
        }

    elapsed = time.time() - t0
    tracer.end("rewrite", elapsed=round(elapsed, 2), action=rewritten["counselor_action"])

    stream_progress(
        session_id=session_id,
        query_id=query_id,
        step="query_rewrite",
        status="done",
        message=(
            f"Rewrite done ({elapsed:.2f}s). action={rewritten['counselor_action']}; "
            f"resolved='{rewritten['resolved_query'][:80]}'"
        ),
        elapsed=round(elapsed, 3),
    )

    return {
        **rewritten,
        "current_step": "query_rewrite",
        "step_timings": {
            **state.get("step_timings", {}),
            "query_rewrite": round(elapsed, 3),
        },
    }
