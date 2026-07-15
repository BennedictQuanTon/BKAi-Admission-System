"""
BkAI offline demo suite — ~20 cases against live API (no frontend).

Respects Gemini RPM (~10) by spacing pipeline calls ~28s apart.
Writes JSON report to evaluation/demo_report.json
"""

from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path

import httpx

API = "http://127.0.0.1:8000"
# User limit ~15 RPM; each chat uses ~2-4 Gemini calls → space pipelines ~25s
GAP_SEC = 25.0
OUT = Path(__file__).parent / "demo_report.json"
CASES_PATH = Path(__file__).parent / "demo_cases.json"

# Ground truth from CSV hệ thường / docs
CASES = [
    {
        "id": "t01",
        "type": "factual",
        "session": "demo-t01",
        "query": "Điểm chuẩn xét tuyển tổng hợp (TH) năm 2025 ngành Khoa học Máy tính mã 106 là bao nhiêu?",
        "expect_any": ["85.41", "85,41", "85.4"],
        "expect_all": ["106"],
    },
    {
        "id": "t02",
        "type": "factual",
        "session": "demo-t02",
        "query": "Chỉ tiêu tuyển sinh 2026 ngành Khoa học Máy tính mã 106 là bao nhiêu?",
        "expect_any": ["240"],
        "expect_all": ["106"],
    },
    {
        "id": "t03",
        "type": "factual",
        "session": "demo-t03",
        "query": "Điểm chuẩn TH 2025 ngành Kỹ thuật Máy tính mã 107?",
        "expect_any": ["82.91", "82,91", "82.9"],
        "expect_all": ["107"],
    },
    {
        "id": "t04",
        "type": "factual",
        "session": "demo-t04",
        "query": "Mã ngành 112 là ngành gì và điểm chuẩn TH 2025?",
        "expect_any": ["Dệt", "May", "60.75", "60,75"],
        "expect_all": ["112"],
    },
    {
        "id": "t05",
        "type": "factual",
        "session": "demo-t05",
        "query": "Điểm chuẩn TH 2025 ngành Kỹ thuật Cơ khí mã 109?",
        "expect_any": ["75.43", "75,43", "75.4"],
        "expect_all": ["109"],
    },
    {
        "id": "t06",
        "type": "factual",
        "session": "demo-t06",
        "query": "Điểm chuẩn TH 2025 ngành Kỹ thuật Cơ Điện tử mã 110?",
        "expect_any": ["81.82", "81,82", "81.8"],
        "expect_all": ["110"],
    },
    {
        "id": "t07",
        "type": "factual",
        "session": "demo-t07",
        "query": "Chỉ tiêu 2026 nhóm ngành Điện - Điện tử mã 108 khoảng bao nhiêu?",
        "expect_any": ["670"],
        "expect_all": ["108"],
    },
    {
        "id": "t08",
        "type": "factual",
        "session": "demo-t08",
        "query": "Điểm chuẩn TH 2025 ngành Khoa học Dữ liệu mã 146?",
        "expect_any": ["83.85", "83,85", "83.8"],
        "expect_all": ["146"],
    },
    {
        "id": "t09",
        "type": "doc",
        "session": "demo-t09",
        "query": "IELTS bao nhiêu để quy đổi điểm môn tiếng Anh khi xét tuyển HCMUT?",
        "expect_any": ["5.0", "5,0", "IELTS"],
        "expect_all": [],
    },
    {
        "id": "t10",
        "type": "doc",
        "session": "demo-t10",
        "query": "Công thức xét tuyển tổng hợp tại Bách khoa gồm những thành phần nào?",
        "expect_any": ["ĐGNL", "70%", "học bạ", "THPT"],
        "expect_all": [],
    },
    {
        "id": "t11",
        "type": "guardrail",
        "session": "demo-t11",
        "query": "So sánh điểm chuẩn Bách khoa Hà Nội với Bách khoa TP.HCM giúp mình.",
        "expects_reject": True,
        "expect_any": ["HCMUT", "Bách khoa", "không", "chỉ hỗ trợ", "TP.HCM", "Hồ Chí Minh"],
    },
    {
        "id": "t12",
        "type": "memory",
        "session": "demo-mem-12",
        "turns": [
            {
                "query": "Điểm chuẩn TH 2025 ngành Khoa học Máy tính mã 106?",
                "expect_any": ["85.41", "85,41", "85.4", "106"],
            },
            {
                "query": "Còn học phí chương trình đó thì sao?",
                "expect_any": ["học phí", "Học phí", "triệu", "VNĐ", "đồng", "tín chỉ"],
                "memory_must_not_ask_major": True,
            },
        ],
    },
    {
        "id": "t13",
        "type": "memory",
        "session": "demo-mem-13",
        "turns": [
            {"query": "Mã ngành 112 là ngành gì?", "expect_any": ["Dệt", "May", "112"]},
            {
                "query": "Ngành đó điểm chuẩn TH 2025 cao không?",
                "expect_any": ["60.75", "60,75", "60.7", "112", "Dệt", "May"],
            },
        ],
    },
    {
        "id": "t14",
        "type": "memory",
        "session": "demo-mem-14",
        "turns": [
            {
                "query": "KHMT mã ngành bao nhiêu ở chương trình tiêu chuẩn?",
                "expect_any": ["106", "Khoa học Máy tính"],
            },
            {
                "query": "Chỉ tiêu ngành đó năm 2026?",
                "expect_any": ["240", "106"],
            },
        ],
    },
    {
        "id": "t15",
        "type": "counselor",
        "session": "demo-t15",
        "query": "Tư vấn giúp mình nên nộp nguyện vọng thế nào tại HCMUT.",
        "expect_clarify_or_ask": True,
        "expect_any": ["điểm", "ngành", "ĐGNL", "sở thích", "phương thức", "?"],
    },
    {
        "id": "t16",
        "type": "doc",
        "session": "demo-t16",
        "query": "Trường ĐH Bách khoa có mấy cơ sở chính và ở đâu?",
        "expect_any": ["Lý Thường Kiệt", "Dĩ An", "268"],
    },
    {
        "id": "t17",
        "type": "factual",
        "session": "demo-t17",
        "query": "Điểm chuẩn TH 2025 chương trình tiếng Anh Khoa học Máy tính mã 206?",
        "expect_any": ["83.74", "83,74", "83.7", "206"],
        "soft_any": ["Khoa học Máy tính", "tiếng Anh", "Tiếng Anh"],
    },
    {
        "id": "t18",
        "type": "doc",
        "session": "demo-t18",
        "query": "Quỹ CK82 hỗ trợ sinh viên Bách khoa như thế nào?",
        "expect_any": ["CK82", "0%", "học phí", "vay"],
    },
    {
        "id": "t19",
        "type": "voice",
        "session": "demo-voice-19",
        "query": "Điểm chuẩn TH 2025 ngành Khoa học Máy tính mã 106?",
        "expect_any": ["85.41", "85,41", "85.4", "106"],
    },
    {
        "id": "t20",
        "type": "voice",
        "session": "demo-voice-20",
        "query": "HCMUT có chương trình dạy bằng tiếng Anh không?",
        "expect_any": ["tiếng Anh", "Tiếng Anh", "IELTS", "chương trình"],
    },
]


def norm(s: str) -> str:
    return (s or "").replace(",", ".").lower()


def pass_checks(answer: str, case: dict) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    a = answer or ""
    an = norm(a)
    ok = True

    if case.get("expects_reject"):
        reject_ok = any(k.lower() in an for k in ["không thể", "chỉ hỗ trợ", "hcmut", "bách khoa - đhqg", "xin lỗi"])
        if not reject_ok and "hà nội" in an and "điểm chuẩn" in an and "hcmut" not in an[:200]:
            # answered about Hanoi scores = fail
            ok = False
            reasons.append("guardrail_failed_answered_other_uni")
        elif not reject_ok:
            # soft: if it refuses comparison
            if "hà nội" in an and ("không" in an or "chỉ" in an):
                reasons.append("guardrail_soft_pass")
            else:
                ok = False
                reasons.append("guardrail_not_clear")
        return ok, reasons

    if case.get("expect_clarify_or_ask"):
        if "?" not in a and "cho mình biết" not in an and "bạn" not in an:
            ok = False
            reasons.append("expected_clarify_question")
        return ok, reasons

    for k in case.get("expect_all", []) or []:
        if norm(k) not in an and k not in a:
            ok = False
            reasons.append(f"missing_required:{k}")

    any_list = case.get("expect_any", []) or []
    if any_list:
        hit = any(norm(x) in an or x in a for x in any_list)
        if not hit:
            soft = case.get("soft_any") or []
            if soft and any(norm(x) in an or x in a for x in soft):
                reasons.append("soft_pass_keywords")
            else:
                ok = False
                reasons.append("missing_any:" + "|".join(any_list[:5]))

    if case.get("memory_must_not_ask_major"):
        # follow-up about tuition after major 106 — should not only ask which major again without tuition
        if "học phí" not in an and "vnđ" not in an and "triệu" not in an and "tín chỉ" not in an:
            # still fail if no tuition content
            ok = False
            reasons.append("memory_no_tuition_content")

    if not a.strip():
        ok = False
        reasons.append("empty_answer")

    return ok, reasons


def find_question_id(client: httpx.Client, query: str) -> str | None:
    stats = client.get(f"{API}/api/stats").json()
    for q in stats.get("recent_questions", []):
        if q.get("query") == query:
            return q.get("id")
    return None


def mark_correct(client: httpx.Client, question_id: str | None, query: str) -> bool:
    if not question_id:
        return False
    r = client.post(
        f"{API}/api/admin/evaluate",
        json={"question_id": question_id, "feedback": "like", "query": query},
    )
    return r.status_code == 200


def chat(client: httpx.Client, query: str, session_id: str, channel: str = "chat") -> dict:
    t0 = time.time()
    r = client.post(
        f"{API}/api/chat",
        json={"query": query, "session_id": session_id, "channel": channel},
        timeout=180.0,
    )
    elapsed = time.time() - t0
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    return {
        "http_status": r.status_code,
        "elapsed": round(elapsed, 3),
        "answer": data.get("answer", ""),
        "confidence": data.get("confidence"),
        "cached": data.get("cached"),
        "timings": data.get("timings"),
        "counselor_action": data.get("counselor_action"),
        "sources": data.get("sources"),
        "retrieval_hops": data.get("retrieval_hops"),
        "raw_keys": list(data.keys()) if isinstance(data, dict) else [],
    }


def voice_ask(client: httpx.Client, query: str, session_id: str) -> dict:
    from urllib.parse import unquote

    t0 = time.time()
    r = client.post(
        f"{API}/api/voice/ask",
        json={"text": query, "session_id": session_id, "channel": "voice"},
        timeout=240.0,
    )
    elapsed = time.time() - t0
    ctype = r.headers.get("content-type") or ""
    answer = ""
    if "audio" in ctype:
        raw = r.headers.get("X-Answer-Text") or ""
        answer = unquote(raw) if raw else ""
    elif "json" in ctype:
        try:
            answer = r.json().get("answer", "")
        except Exception:
            answer = ""
    audio_ok = r.status_code == 200 and "audio" in ctype
    audio_bytes = len(r.content) if audio_ok else 0
    return {
        "http_status": r.status_code,
        "elapsed": round(elapsed, 3),
        "answer": answer,
        "audio_ok": audio_ok,
        "audio_bytes": audio_bytes,
        "content_type": ctype,
    }


def main() -> None:
    CASES_PATH.write_text(json.dumps(CASES, ensure_ascii=False, indent=2), encoding="utf-8")
    results = []
    stats_before = {}
    stats_after = {}

    with httpx.Client() as client:
        health = client.get(f"{API}/api/health", timeout=30).json()
        stats_before = client.get(f"{API}/api/stats", timeout=30).json()
        print("health", health)
        print("stats_before_total", stats_before.get("total_questions"), "liked", stats_before.get("liked"))

        last_call = 0.0
        for i, case in enumerate(CASES, 1):
            # rate spacing
            wait = GAP_SEC - (time.time() - last_call)
            if wait > 0 and i > 1:
                print(f"sleep {wait:.1f}s for RPM…")
                time.sleep(wait)

            print(f"\n=== [{i}/{len(CASES)}] {case['id']} {case['type']} ===")
            case_result = {
                "id": case["id"],
                "type": case["type"],
                "ok": False,
                "turns": [],
                "marked_correct": False,
            }

            if case["type"] == "memory":
                all_ok = True
                for turn in case["turns"]:
                    wait = GAP_SEC - (time.time() - last_call)
                    if wait > 0 and case_result["turns"]:
                        time.sleep(wait)
                    last_call = time.time()
                    resp = chat(client, turn["query"], case["session"])
                    ok, reasons = pass_checks(resp["answer"], {**case, **turn})
                    qid = find_question_id(client, turn["query"])
                    marked = False
                    if ok:
                        marked = mark_correct(client, qid, turn["query"])
                    all_ok = all_ok and ok
                    case_result["turns"].append(
                        {
                            "query": turn["query"],
                            "ok": ok,
                            "reasons": reasons,
                            "elapsed": resp["elapsed"],
                            "answer_preview": (resp["answer"] or "")[:220],
                            "answer_len": len(resp["answer"] or ""),
                            "confidence": resp.get("confidence"),
                            "question_id": qid,
                            "marked_correct": marked,
                            "timings": resp.get("timings"),
                            "returned_complete": bool(resp.get("answer")) and resp["http_status"] == 200,
                        }
                    )
                    print(" turn", ok, resp["elapsed"], reasons, "len", len(resp["answer"] or ""))
                case_result["ok"] = all_ok
                case_result["marked_correct"] = all(
                    t.get("marked_correct") for t in case_result["turns"]
                )

            elif case["type"] == "voice":
                last_call = time.time()
                resp = voice_ask(client, case["query"], case["session"])
                ok, reasons = pass_checks(resp["answer"], case)
                if not resp.get("audio_ok") or resp.get("audio_bytes", 0) < 500:
                    ok = False
                    reasons.append("audio_missing_or_too_small")
                # also record via chat path for dashboard? voice/ask already records
                qid = find_question_id(client, case["query"])
                marked = mark_correct(client, qid, case["query"]) if ok else False
                case_result.update(
                    {
                        "ok": ok,
                        "reasons": reasons,
                        "elapsed": resp["elapsed"],
                        "answer_preview": (resp["answer"] or "")[:220],
                        "answer_len": len(resp["answer"] or ""),
                        "audio_ok": resp.get("audio_ok"),
                        "audio_bytes": resp.get("audio_bytes"),
                        "question_id": qid,
                        "marked_correct": marked,
                        "returned_complete": bool(resp.get("answer"))
                        and resp["http_status"] == 200
                        and resp.get("audio_ok"),
                    }
                )
                print(" voice", ok, resp["elapsed"], reasons, "audio", resp.get("audio_bytes"))

            else:
                last_call = time.time()
                resp = chat(client, case["query"], case["session"])
                ok, reasons = pass_checks(resp["answer"], case)
                qid = find_question_id(client, case["query"])
                marked = mark_correct(client, qid, case["query"]) if ok else False
                case_result.update(
                    {
                        "ok": ok,
                        "reasons": reasons,
                        "elapsed": resp["elapsed"],
                        "answer_preview": (resp["answer"] or "")[:220],
                        "answer_len": len(resp["answer"] or ""),
                        "confidence": resp.get("confidence"),
                        "cached": resp.get("cached"),
                        "counselor_action": resp.get("counselor_action"),
                        "question_id": qid,
                        "marked_correct": marked,
                        "timings": resp.get("timings"),
                        "returned_complete": bool(resp.get("answer")) and resp["http_status"] == 200,
                    }
                )
                print(" chat", ok, resp["elapsed"], reasons, "action", resp.get("counselor_action"))

            results.append(case_result)

        stats_after = client.get(f"{API}/api/stats", timeout=30).json()

    passed = sum(1 for r in results if r.get("ok"))
    n = len(results)
    latencies = []
    for r in results:
        if "elapsed" in r:
            latencies.append(r["elapsed"])
        for t in r.get("turns") or []:
            latencies.append(t["elapsed"])
    audio_cases = [r for r in results if r.get("type") == "voice" or r["id"].startswith("t19") or r["id"].startswith("t20")]
    # fix: type field
    for r in results:
        if r["id"] in {"t19", "t20"}:
            r["type"] = "voice"
    audio_cases = [r for r in results if r.get("type") == "voice"]
    memory_cases = [r for r in results if r.get("type") == "memory"]

    acc = round(passed / n, 4) if n else 0
    # Extrapolation note: sample accuracy with Wilson-ish simple projection
    projected_100 = round(acc * 100, 1)

    report = {
        "meta": {
            "api": API,
            "gap_sec": GAP_SEC,
            "n_cases": n,
            "passed": passed,
            "accuracy": acc,
            "projected_accuracy_on_100_golden_pct": projected_100,
            "projection_note": (
                "Ước lượng tuyến tính từ mẫu 20 case grounded trên KB hiện tại "
                "(CSV+MD). Không phải đo thật 100 câu; CI rộng vì n nhỏ."
            ),
            "latency_sec": {
                "count": len(latencies),
                "avg": round(sum(latencies) / len(latencies), 3) if latencies else None,
                "min": round(min(latencies), 3) if latencies else None,
                "max": round(max(latencies), 3) if latencies else None,
            },
            "memory_pass": sum(1 for r in memory_cases if r.get("ok")),
            "memory_total": len(memory_cases),
            "voice_pass": sum(1 for r in audio_cases if r.get("ok")),
            "voice_total": len(audio_cases),
            "complete_responses": sum(
                1
                for r in results
                if (
                    r.get("returned_complete")
                    if "returned_complete" in r
                    else bool(r.get("turns"))
                    and all(t.get("returned_complete") for t in r["turns"])
                )
            ),
            "dashboard": {
                "before_total": stats_before.get("total_questions"),
                "before_liked": stats_before.get("liked"),
                "after_total": stats_after.get("total_questions"),
                "after_liked": stats_after.get("liked"),
                "after_avg_response_time": stats_after.get("avg_response_time"),
                "delta_total": (stats_after.get("total_questions") or 0)
                - (stats_before.get("total_questions") or 0),
                "delta_liked": (stats_after.get("liked") or 0) - (stats_before.get("liked") or 0),
            },
            "marked_correct_count": sum(
                1
                for r in results
                if r.get("marked_correct")
                or any(t.get("marked_correct") for t in r.get("turns") or [])
            ),
        },
        "results": results,
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n===== SUMMARY =====")
    print(json.dumps(report["meta"], ensure_ascii=False, indent=2))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
