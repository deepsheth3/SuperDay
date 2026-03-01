"""Session state (in-memory)."""
from __future__ import annotations

import uuid

from harper_agent.models import ActiveFocus, SessionState, TurnRecord

_sessions: dict[str, SessionState] = {}


def get_session(session_id: str) -> SessionState:
    if session_id in _sessions:
        return _sessions[session_id]
    s = SessionState(session_id=session_id)
    _sessions[session_id] = s
    return s


def save_session(session_id: str, state: SessionState) -> None:
    _sessions[session_id] = state


def create_session_id() -> str:
    return str(uuid.uuid4())


def append_turn(
    state: SessionState,
    role: str,
    message: str,
    resolved_account_id: str | None = None,
    resolved_person_id: str | None = None,
    list_items: list[str] | None = None,
    references: list[dict] | None = None,
) -> None:
    state.turn_history.append(
        TurnRecord(
            role=role,
            message=message,
            resolved_account_id=resolved_account_id,
            resolved_person_id=resolved_person_id,
            list_items=list_items,
            references=references,
        )
    )


def set_active_focus(state: SessionState, focus_type: str, focus_id: str, confidence: float = 1.0) -> None:
    state.active_focus = ActiveFocus(type=focus_type, id=focus_id, confidence=confidence)
