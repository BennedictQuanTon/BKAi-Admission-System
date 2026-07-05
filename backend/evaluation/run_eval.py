"""
Run RAG evaluation against golden set using Gemini as judge.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from services.guardrails import GuardrailDecision, enforce_guardrails
from workflows.main_graph import run_agent_pipeline

GOLDEN_PATH = Path(__file__).parent / "golden_set.json"


async def run_eval(limit: int | None = None) -> dict:
    cases = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    if limit:
        cases = cases[:limit]

    results = []
    passed = 0

    for case in cases:
        question = case["question"]
        expects_reject = case.get("expects_reject", False)

        guard = await enforce_guardrails(question)
        if expects_reject:
            ok = guard.decision == GuardrailDecision.REJECT
            passed += int(ok)
            results.append({"id": case["id"], "ok": ok, "mode": "guardrail"})
            continue

        if guard.decision == GuardrailDecision.REJECT:
            results.append({"id": case["id"], "ok": False, "mode": "unexpected_reject"})
            continue

        pipeline = await run_agent_pipeline(question, session_id=f"eval-{case['id']}")
        ok = bool(pipeline.get("answer")) and pipeline.get("confidence", 0) >= 0.5
        passed += int(ok)
        results.append({
            "id": case["id"],
            "ok": ok,
            "confidence": pipeline.get("confidence"),
            "answer_preview": pipeline.get("answer", "")[:120],
        })

    summary = {
        "total": len(cases),
        "passed": passed,
        "pass_rate": round(passed / max(len(cases), 1), 4),
        "results": results,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    asyncio.run(run_eval())
