from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class SessionState:
    session_id: str
    user_id: str
    last_user_text: str | None = None
    last_agent_text: str | None = None
    last_tool_answer: str = ""
    pending_tool_answer: str = ""
    current_topics: list[str] = field(default_factory=list)
    turns: list[dict[str, str]] = field(default_factory=list)
    persistent_memory_prompt: str = ""
    proactive_prompt: str = ""
    last_reconnect_reason: str | None = None
    last_memory_write_status: str | None = None
    last_error: str | None = None
    context_dispatched: bool = False
    user_context: dict[str, str] = field(default_factory=dict)
    memory_context: dict[str, Any] = field(default_factory=dict)
    demo_mode: bool = False
    demo_index: int = 0
    demo_pending_text: str = ""
    demo_pending_sent: bool = False
    demo_finish_after_pending: bool = False
    demo_allow_audio: bool = False
    demo_final_pending: bool = False
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def touch(self) -> None:
        self.updated_at = _utcnow()


class SessionStateStore:
    """In-process reconnect cache with TTL and basic stats."""

    def __init__(self, ttl_minutes: int = 15):
        self._ttl = timedelta(minutes=max(ttl_minutes, 1))
        self._items: dict[tuple[str, str], SessionState] = {}

    def _key(self, user_id: str, session_id: str) -> tuple[str, str]:
        return (user_id, session_id)

    def _is_expired(self, state: SessionState) -> bool:
        return (_utcnow() - state.updated_at) > self._ttl

    def sweep_expired(self) -> int:
        expired = [key for key, state in self._items.items() if self._is_expired(state)]
        for key in expired:
            del self._items[key]
        if expired:
            logger.info("session_state_swept", removed=len(expired))
        return len(expired)

    def get_or_create(self, user_id: str, session_id: str) -> SessionState:
        self.sweep_expired()
        key = self._key(user_id, session_id)
        state = self._items.get(key)
        if state and not self._is_expired(state):
            state.touch()
            return state

        state = SessionState(session_id=session_id, user_id=user_id)
        self._items[key] = state
        logger.info("session_state_created", user_id=user_id, session_id=session_id)
        return state

    def get(self, user_id: str, session_id: str) -> SessionState | None:
        self.sweep_expired()
        state = self._items.get(self._key(user_id, session_id))
        if not state:
            return None
        if self._is_expired(state):
            self.delete(user_id, session_id)
            return None
        state.touch()
        return state

    def update(self, user_id: str, session_id: str, **changes: Any) -> SessionState:
        state = self.get_or_create(user_id, session_id)
        for key, value in changes.items():
            setattr(state, key, value)
        state.touch()
        return state

    def delete(self, user_id: str, session_id: str) -> None:
        self._items.pop(self._key(user_id, session_id), None)
        logger.info("session_state_deleted", user_id=user_id, session_id=session_id)

    def stats(self) -> dict[str, Any]:
        self.sweep_expired()
        oldest_age_seconds = 0.0
        if self._items:
            oldest = min(self._items.values(), key=lambda state: state.updated_at)
            oldest_age_seconds = max((_utcnow() - oldest.updated_at).total_seconds(), 0.0)
        return {
            "active_sessions": len(self._items),
            "ttl_minutes": int(self._ttl.total_seconds() // 60),
            "oldest_entry_age_seconds": round(oldest_age_seconds, 2),
        }

    def snapshot(self) -> list[dict[str, Any]]:
        self.sweep_expired()
        snapshots: list[dict[str, Any]] = []
        for state in self._items.values():
            snapshots.append(
                {
                    "user_id": state.user_id,
                    "session_id": state.session_id,
                    "last_reconnect_reason": state.last_reconnect_reason,
                    "last_memory_write_status": state.last_memory_write_status,
                    "last_error": state.last_error,
                    "turn_count": len(state.turns),
                    "topic_count": len(state.current_topics),
                    "updated_at": state.updated_at.isoformat(),
                }
            )
        return snapshots
