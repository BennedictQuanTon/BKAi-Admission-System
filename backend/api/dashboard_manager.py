"""
Dashboard WebSocket Manager.

Tracks connected clients on /ws/dashboard and broadcasts live logs.
"""

from __future__ import annotations

import asyncio
import time
from fastapi import WebSocket
from utils.logger import get_logger

logger = get_logger(__name__)


class DashboardManager:
    def __init__(self) -> None:
        self.active_connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.debug("dashboard_client_connected", count=len(self.active_connections))

    def disconnect(self, websocket: WebSocket) -> None:
        self.active_connections.discard(websocket)
        logger.debug("dashboard_client_disconnected", count=len(self.active_connections))

    async def broadcast(self, message: dict) -> None:
        if not self.active_connections:
            return

        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.active_connections.discard(connection)


dashboard_manager = DashboardManager()


def broadcast_sync(message: dict) -> None:
    """Broadcasting utility safe for synchronous execution contexts (runs on current loop)."""
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            loop.create_task(dashboard_manager.broadcast(message))
    except RuntimeError:
        pass


def stream_progress(
    session_id: str,
    query_id: str,
    step: str,
    status: str,
    message: str,
    elapsed: float | None = None,
    query: str | None = None,
) -> None:
    """Helper to stream progress frames to all connected dashboard clients."""
    broadcast_sync({
        "type": "progress",
        "session_id": session_id,
        "query_id": query_id,
        "query": query,
        "step": step,
        "status": status,
        "message": message,
        "elapsed": elapsed,
        "timestamp": time.time(),
    })
