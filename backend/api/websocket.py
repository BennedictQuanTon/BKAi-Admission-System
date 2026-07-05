"""
BkAI WebSocket Handler — streaming tokens + guardrails.
"""

from __future__ import annotations

import json
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from memory.conversation import get_conversation_memory
from memory.semantic_cache import check_cache, record_question, store_in_cache
from services.guardrails import GuardrailDecision, enforce_guardrails
from services.stream_context import set_token_callback
from utils.logger import get_logger
from utils.text_cleaning import sanitize_input
from workflows.main_graph import run_agent_pipeline

logger = get_logger(__name__)
ws_router = APIRouter()


@ws_router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    await websocket.accept()
    logger.info("ws_connected")

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            query = sanitize_input(data.get("query", ""))
            session_id = data.get("session_id", "default")

            if not query:
                await websocket.send_json({"type": "error", "message": "Empty query"})
                continue

            t0 = time.time()

            guard = await enforce_guardrails(query)
            if guard.decision == GuardrailDecision.REJECT:
                await websocket.send_json({
                    "type": "done",
                    "answer": guard.rejection_message,
                    "metadata": {
                        "cached": False,
                        "guardrail": True,
                        "confidence": 1.0,
                        "response_time": round(time.time() - t0, 3),
                    },
                })
                continue

            cached = check_cache(query)
            if cached:
                response_time = time.time() - t0
                await websocket.send_json({
                    "type": "done",
                    "answer": cached["answer"],
                    "metadata": {
                        "cached": True,
                        "confidence": cached.get("confidence", 1.0),
                        "response_time": round(response_time, 3),
                    },
                })
                record_question(query, cached["answer"], response_time, 0.0, cached=True)
                continue

            await websocket.send_json({"type": "status", "message": "Đang tìm kiếm thông tin..."})

            async def on_token(token: str) -> None:
                await websocket.send_json({"type": "token", "content": token})

            set_token_callback(on_token)

            try:
                await websocket.send_json({"type": "status", "message": "Đang viết câu trả lời..."})
                result = await run_agent_pipeline(query=query, session_id=session_id)
            except Exception as e:
                logger.error("ws_pipeline_error", error=str(e))
                await websocket.send_json({
                    "type": "error",
                    "message": "Xin lỗi, có lỗi xảy ra khi xử lý.",
                })
                continue
            finally:
                set_token_callback(None)

            response_time = time.time() - t0

            await websocket.send_json({
                "type": "done",
                "answer": result["answer"],
                "metadata": {
                    "cached": False,
                    "confidence": result.get("confidence", 0.0),
                    "sources": result.get("sources", []),
                    "timings": result.get("timings", {}),
                    "response_time": round(response_time, 3),
                    "retrieval_hops": result.get("retrieval_hops", 0),
                },
            })

            store_in_cache(
                query=query,
                answer=result["answer"],
                confidence=result.get("confidence", 0.0),
                timings=result.get("timings"),
                sources=result.get("sources"),
            )
            record_question(
                query=query,
                answer=result["answer"],
                response_time=response_time,
                build_time=result.get("timings", {}).get("total", 0.0),
                cached=False,
                trace={
                    "rewritten_queries": result.get("rewritten_queries", []),
                    "sources": result.get("sources", []),
                    "confidence": result.get("confidence", 0.0),
                    "retrieval_hops": result.get("retrieval_hops", 0),
                    "retrieval_decision": result.get("retrieval_decision", ""),
                    "step_timings": result.get("timings", {}),
                },
            )

    except WebSocketDisconnect:
        logger.info("ws_disconnected")
    except Exception as e:
        logger.error("ws_error", error=str(e))
