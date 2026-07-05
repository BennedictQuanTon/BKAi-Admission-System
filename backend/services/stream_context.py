"""Token streaming callback registry for WebSocket responses."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

TokenCallback = Callable[[str], Awaitable[None]]

_callback: TokenCallback | None = None


def set_token_callback(callback: TokenCallback | None) -> None:
    global _callback
    _callback = callback


async def emit_token(token: str) -> None:
    if _callback and token:
        await _callback(token)
