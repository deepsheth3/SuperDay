"""Session state (in-memory). Smart session history: capped turns, rolling summary, recent entities."""
from __future__ import annotations

import uuid

from harper_agent.constants import ALLOWED_SESSION_GOALS
from harper_agent.models import ActiveFocus, SessionState, TurnRecord

MAX_RECENT_TURNS = 6
MAX_RECENT_ACCOUNT_IDS = 5
MAX_RECENT_PERSON_IDS = 5
MAX_ROLLING_SUMMARY_WORDS = 300

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


def _word_count(s: str) -> int:
    return len((s or "").split())


def _update_rolling_summary(state: SessionState, dropped_turns: list[TurnRecord]) -> None:
    """Rule-based summary of dropped turns; merge into rolling_summary and cap at MAX_ROLLING_SUMMARY_WORDS."""
    if not dropped_turns:
        return
    parts = []
    for t in dropped_turns:
        if t.resolved_account_id:
            parts.append(f"discussed account {t.resolved_account_id}")
        if t.resolved_person_id:
            parts.append(f"mentioned person {t.resolved_person_id}")
        if t.role == "user" and t.message and not t.resolved_account_id:
            short = (t.message[:60] + "…") if len(t.message) > 60 else t.message
            parts.append(f"user asked: {short}")
    if not parts:
        parts.append("earlier turns in session")
    new_bit = " ".join(parts)
    if state.rolling_summary:
        state.rolling_summary = state.rolling_summary.strip() + " | " + new_bit
    else:
        state.rolling_summary = new_bit
    words = state.rolling_summary.split()
    if len(words) > MAX_ROLLING_SUMMARY_WORDS:
        state.rolling_summary = " ".join(words[-MAX_ROLLING_SUMMARY_WORDS:])


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
    if len(state.turn_history) > MAX_RECENT_TURNS:
        dropped = state.turn_history[:-MAX_RECENT_TURNS]
        state.turn_history = state.turn_history[-MAX_RECENT_TURNS:]
        _update_rolling_summary(state, dropped)


def update_recent_entities(
    state: SessionState,
    account_id: str | None = None,
    person_id: str | None = None,
) -> None:
    """Add id to recent list (most recent last), dedupe, keep at most MAX_RECENT_*_IDS."""
    if account_id:
        out = [aid for aid in state.recent_account_ids if aid != account_id]
        out.append(account_id)
        state.recent_account_ids = out[-MAX_RECENT_ACCOUNT_IDS:]
    if person_id:
        out = [pid for pid in state.recent_person_ids if pid != person_id]
        out.append(person_id)
        state.recent_person_ids = out[-MAX_RECENT_PERSON_IDS:]


def set_last_intent_constraints(state: SessionState, intent: str | None, constraints: dict[str, str] | None) -> None:
    state.last_intent = intent
    state.last_constraints = constraints or {}


def set_session_goal(state: SessionState, goal: str | None) -> None:
    """Set session_goal if goal is in ALLOWED_SESSION_GOALS; otherwise clear it."""
    if goal is None or (isinstance(goal, str) and not goal.strip()):
        state.session_goal = None
        return
    g = goal.strip() if isinstance(goal, str) else ""
    state.session_goal = g if g in ALLOWED_SESSION_GOALS else None


def set_active_focus(state: SessionState, focus_type: str, focus_id: str, confidence: float = 1.0) -> None:
    state.active_focus = ActiveFocus(type=focus_type, id=focus_id, confidence=confidence)
