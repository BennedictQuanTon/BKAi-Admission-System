"""
BkAI Conversation Memory.

Per-session sliding window history + ephemeral student profile.
Session-only (in-RAM): cleared on New chat / explicit clear — no User DB.
"""

from __future__ import annotations

from collections import defaultdict

from memory.student_profile import StudentProfile
from utils.logger import get_logger

logger = get_logger(__name__)

MAX_HISTORY_TURNS = 12  # ~6 exchanges


class ConversationMemory:
    def __init__(self, max_turns: int = MAX_HISTORY_TURNS) -> None:
        self._sessions: dict[str, list[dict[str, str]]] = defaultdict(list)
        self._profiles: dict[str, StudentProfile] = {}
        self._max_turns = max_turns

    def add_turn(self, session_id: str, role: str, content: str) -> None:
        history = self._sessions[session_id]
        history.append({"role": role, "content": content})
        if len(history) > self._max_turns:
            self._sessions[session_id] = history[-self._max_turns :]

    def get_history(self, session_id: str) -> list[dict[str, str]]:
        return list(self._sessions.get(session_id, []))

    def get_profile(self, session_id: str) -> StudentProfile:
        if session_id not in self._profiles:
            self._profiles[session_id] = StudentProfile()
        return self._profiles[session_id]

    def update_profile(self, session_id: str, patch: dict) -> StudentProfile:
        current = self.get_profile(session_id)
        updated = current.merge_patch(patch or {})
        self._profiles[session_id] = updated
        return updated

    def clear_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        self._profiles.pop(session_id, None)

    def active_sessions(self) -> int:
        return len(self._sessions)


_memory = ConversationMemory()


def get_conversation_memory() -> ConversationMemory:
    return _memory
