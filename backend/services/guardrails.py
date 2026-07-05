"""
BkAI Guardrails — restrict scope to HCMUT admissions counseling only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from config.settings import get_settings
from utils.logger import get_logger

logger = get_logger(__name__)


class GuardrailDecision(str, Enum):
    ALLOW = "allow"
    REJECT = "reject"
    UNCERTAIN = "uncertain"


@dataclass
class GuardrailResult:
    decision: GuardrailDecision
    reason: str = ""
    rejection_message: str = ""


OTHER_UNI_PATTERNS = [
    r"bách\s*khoa\s*hà\s*nội",
    r"đh\s*bk\s*hn",
    r"đhbk\s*hn",
    r"\bhust\b",
    r"bách\s*khoa\s*đà\s*nẵng",
    r"\brmit\b",
    r"\bfpt\b",
    r"đại\s*học\s*quốc\s*gia\s*hà\s*nội",
    r"đh\s*quốc\s*gia\s*hn",
    r"đại\s*học\s*bách\s*khoa\s*tp\s*hà\s*nội",
]

OFF_TOPIC_PATTERNS = [
    r"\bviết\s+code\b",
    r"\bpython\b.*\bcode\b",
    r"\bbài\s+tập\b",
    r"\bthời\s+tiết\b",
    r"\bchính\s+trị\b",
    r"\btin\s+tức\b",
    r"\bgame\b",
    r"\bphim\b",
]

HCMUT_SCOPE_PATTERNS = [
    r"\bhcmut\b",
    r"bách\s*khoa",
    r"\bbk\b",
    r"tuyển\s*sinh",
    r"điểm\s*chuẩn",
    r"học\s*phí",
    r"ngành\s*học",
    r"chỉ\s*tiêu",
    r"xét\s*tuyển",
    r"đgnl",
    r"đánh\s*giá\s*năng\s*lực",
    r"hồ\s*sơ",
    r"chương\s*trình",
    r"học\s*bổng",
    r"mã\s*ngành",
    r"hcmut\.edu\.vn",
    r"đhqg[\s-]*hcm",
    r"đại\s*học\s*bách\s*khoa",
    r"tp\.?\s*hcm",
    r"thành\s*phố\s*hồ\s*chí\s*minh",
]

REJECTION_TEMPLATE = (
    "Xin lỗi, **BkAI** chỉ hỗ trợ tư vấn tuyển sinh **Trường Đại học Bách khoa - ĐHQG-HCM (HCMUT)**.\n\n"
    "Tôi không thể trả lời câu hỏi {reason_detail}.\n\n"
    "Bạn có thể hỏi về điểm chuẩn, ngành học, học phí, chương trình đào tạo, "
    "hoặc phương thức xét tuyển tại HCMUT."
)


def _normalize(text: str) -> str:
    return text.lower().strip()


def _matches_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def check_guardrails(query: str) -> GuardrailResult:
    """Rule-based guardrail check (no API call)."""
    settings = get_settings()
    if not settings.guardrails.enabled:
        return GuardrailResult(decision=GuardrailDecision.ALLOW)

    text = _normalize(query)
    if not text:
        return GuardrailResult(
            decision=GuardrailDecision.REJECT,
            reason="empty_query",
            rejection_message=REJECTION_TEMPLATE.format(
                reason_detail="vì câu hỏi trống"
            ),
        )

    if _matches_any(text, OTHER_UNI_PATTERNS):
        return GuardrailResult(
            decision=GuardrailDecision.REJECT,
            reason="other_university",
            rejection_message=REJECTION_TEMPLATE.format(
                reason_detail="về trường đại học khác (không phải HCMUT)"
            ),
        )

    if _matches_any(text, OFF_TOPIC_PATTERNS):
        return GuardrailResult(
            decision=GuardrailDecision.REJECT,
            reason="off_topic",
            rejection_message=REJECTION_TEMPLATE.format(
                reason_detail="ngoài phạm vi tư vấn tuyển sinh HCMUT"
            ),
        )

    if _matches_any(text, HCMUT_SCOPE_PATTERNS):
        return GuardrailResult(decision=GuardrailDecision.ALLOW)

    # Greeting / short follow-ups in conversation
    if len(text) <= 20 and re.match(
        r"^(xin\s*chào|chào|cảm\s*ơn|ok|oke|ừ|vâng|hi|hello)[\s!.?]*$",
        text,
    ):
        return GuardrailResult(decision=GuardrailDecision.ALLOW)

    return GuardrailResult(
        decision=GuardrailDecision.UNCERTAIN,
        reason="uncertain_scope",
    )


async def classify_with_llm(query: str) -> GuardrailResult:
    """LLM classifier for uncertain queries (uses Flash-Lite)."""
    from langchain_core.messages import HumanMessage, SystemMessage
    from pydantic import BaseModel, Field

    from services.llm_factory import acquire_rpm_slot, get_fast_llm

    class ScopeClassification(BaseModel):
        scope: str = Field(description="IN_SCOPE_HCMUT | OUT_OF_SCOPE_OTHER_UNI | OUT_OF_SCOPE_OFF_TOPIC")
        reason: str = Field(default="")

    prompt = """Phân loại câu hỏi cho chatbot tư vấn tuyển sinh HCMUT (ĐH Bách khoa - ĐHQG-HCM).
- IN_SCOPE_HCMUT: liên quan tuyển sinh/đào tạo HCMUT
- OUT_OF_SCOPE_OTHER_UNI: hỏi về trường khác (BK Hà Nội, RMIT, FPT...)
- OUT_OF_SCOPE_OFF_TOPIC: không liên quan tuyển sinh HCMUT"""

    try:
        await acquire_rpm_slot("fast")
        llm = get_fast_llm().with_structured_output(ScopeClassification)
        result: ScopeClassification = await llm.ainvoke([
            SystemMessage(content=prompt),
            HumanMessage(content=f"Câu hỏi: {query}"),
        ])

        if result.scope == "IN_SCOPE_HCMUT":
            return GuardrailResult(decision=GuardrailDecision.ALLOW)
        if result.scope == "OUT_OF_SCOPE_OTHER_UNI":
            return GuardrailResult(
                decision=GuardrailDecision.REJECT,
                reason="other_university_llm",
                rejection_message=REJECTION_TEMPLATE.format(
                    reason_detail="về trường đại học khác (không phải HCMUT)"
                ),
            )
        return GuardrailResult(
            decision=GuardrailDecision.REJECT,
            reason="off_topic_llm",
            rejection_message=REJECTION_TEMPLATE.format(
                reason_detail="ngoài phạm vi tư vấn tuyển sinh HCMUT"
            ),
        )
    except Exception as e:
        logger.warning("guardrail_llm_failed", error=str(e))
        return GuardrailResult(decision=GuardrailDecision.ALLOW)


async def enforce_guardrails(query: str) -> GuardrailResult:
    """Full guardrail pipeline: rules first, LLM only if uncertain."""
    result = check_guardrails(query)
    if result.decision == GuardrailDecision.UNCERTAIN:
        return await classify_with_llm(query)
    return result
