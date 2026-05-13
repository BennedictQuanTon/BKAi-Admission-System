"""
BKAi Conversation Memory.

Manages per-session conversation history with sliding window.
"""

from __future__ import annotations

from collections import defaultdict

from utils.logger import get_logger

logger = get_logger(__name__)

MAX_HISTORY_TURNS = 10  # Keep last 10 turns (5 exchanges)


class ConversationMemory:
    """
    In-memory conversation history manager.

    Maintains per-session sliding window of chat turns.
    Thread-safe for concurrent sessions via dict isolation.
    """

    def __init__(self, max_turns: int = MAX_HISTORY_TURNS) -> None:
        self._sessions: dict[str, list[dict[str, str]]] = defaultdict(list)
        self._max_turns = max_turns

    def add_turn(self, session_id: str, role: str, content: str) -> None:
        """Add a conversation turn."""
        history = self._sessions[session_id]
        history.append({"role": role, "content": content})

        # Trim to max turns
        if len(history) > self._max_turns:
            self._sessions[session_id] = history[-self._max_turns:]

    def get_history(self, session_id: str) -> list[dict[str, str]]:
        """Get conversation history for a session."""
        return list(self._sessions.get(session_id, []))

    def clear_session(self, session_id: str) -> None:
        """Clear a session's history."""
        self._sessions.pop(session_id, None)

    def active_sessions(self) -> int:
        """Number of active sessions."""
        return len(self._sessions)


# Global singleton
_memory = ConversationMemory()


def get_conversation_memory() -> ConversationMemory:
    """Get the global ConversationMemory instance."""
    return _memory
