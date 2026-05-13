"""
BKAi WebSocket Handler.

Provides real-time streaming chat via WebSocket.
"""

from __future__ import annotations

import json
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from memory.semantic_cache import check_cache, store_in_cache, record_question
from memory.conversation import get_conversation_memory
from workflows.main_graph import run_agent_pipeline
from utils.logger import get_logger
from utils.text_cleaning import sanitize_input

logger = get_logger(__name__)
ws_router = APIRouter()


@ws_router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """
    WebSocket endpoint for streaming chat.

    Protocol:
    - Client sends: {"query": "...", "session_id": "..."}
    - Server sends: {"type": "stream", "content": "..."} (tokens)
    - Server sends: {"type": "done", "answer": "...", "metadata": {...}}
    """
    await websocket.accept()
    logger.info("ws_connected")

    try:
        while True:
            # Receive message
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

            # Check cache first
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

            # Send "thinking" status
            await websocket.send_json({"type": "status", "message": "Đang xử lý..."})

            # Run pipeline
            try:
                result = await run_agent_pipeline(query=query, session_id=session_id)
            except Exception as e:
                logger.error("ws_pipeline_error", error=str(e))
                await websocket.send_json({
                    "type": "error",
                    "message": "Xin lỗi, có lỗi xảy ra khi xử lý.",
                })
                continue

            response_time = time.time() - t0

            # Send complete answer
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

            # Cache and record
            store_in_cache(
                query=query, answer=result["answer"],
                confidence=result.get("confidence", 0.0),
                timings=result.get("timings"),
                sources=result.get("sources"),
            )
            record_question(
                query, result["answer"], response_time,
                result.get("timings", {}).get("total", 0.0),
            )

    except WebSocketDisconnect:
        logger.info("ws_disconnected")
    except Exception as e:
        logger.error("ws_error", error=str(e))
