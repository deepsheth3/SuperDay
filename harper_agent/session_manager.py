"""Session state and service. Uses session_store for persistence (design §9.4). Smart session history: capped turns, rolling summary, recent entities."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from harper_agent.constants import ALLOWED_SESSION_GOALS
from harper_agent.models import ActiveFocus, SessionState, TurnRecord
from harper_agent.session_store import get_session as _store_get, save_session as _store_save

MAX_RECENT_TURNS = 6
MAX_RECENT_ACCOUNT_IDS = 5
MAX_RECENT_PERSON_IDS = 5
MAX_ROLLING_SUMMARY_WORDS = 300
MAX_OPEN_THREADS = 5
MAX_RECENT_TOPICS = 5
# MemGPT-style working context cap (chars; ~500 tokens at ~4 chars/token)
MAX_WORKING_CONTEXT_CHARS = 2000


def get_session(session_id: str, *, tenant_id: str | None = None) -> SessionState:
    """Load or create session. Session store is tenant-scoped when tenant_id is provided."""
    state = _store_get(session_id, tenant_id=tenant_id)
    if state is not None:
        return state
    s = SessionState(session_id=session_id, tenant_id=tenant_id)
    _store_save(session_id, s)
    return s


def save_session(session_id: str, state: SessionState) -> None:
    """Update version/updated_at and persist to session store."""
    state.version += 1
    state.updated_at = datetime.now(tz=timezone.utc)
    _store_save(session_id, state)


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
    if intent:
        _push_recent_topic(state, intent)


def _push_open_thread(state: SessionState, label: str) -> None:
    out = [x for x in state.open_threads if x != label]
    out.append(label)
    state.open_threads = out[-MAX_OPEN_THREADS:]


def _push_recent_topic(state: SessionState, topic: str) -> None:
    out = [x for x in state.recent_topics if x != topic]
    out.append(topic)
    state.recent_topics = out[-MAX_RECENT_TOPICS:]


def push_open_thread(state: SessionState, label: str) -> None:
    """Add a thread label (e.g. 'disambiguation'); capped at MAX_OPEN_THREADS."""
    _push_open_thread(state, label)


def clear_open_thread(state: SessionState, label: str) -> None:
    """Remove a thread label when resolved."""
    state.open_threads = [x for x in state.open_threads if x != label]


def set_session_goal(state: SessionState, goal: str | None) -> None:
    """Set session_goal if goal is in ALLOWED_SESSION_GOALS; otherwise clear it."""
    if goal is None or (isinstance(goal, str) and not goal.strip()):
        state.session_goal = None
        return
    g = goal.strip() if isinstance(goal, str) else ""
    state.session_goal = g if g in ALLOWED_SESSION_GOALS else None


def set_active_focus(state: SessionState, focus_type: str, focus_id: str, confidence: float = 1.0) -> None:
    state.active_focus = ActiveFocus(type=focus_type, id=focus_id, confidence=confidence)


# --- MemGPT-style working context (LLM-editable via tools) ---


def working_context_append(state: SessionState, text: str) -> str:
    """Append text to working context. Enforces MAX_WORKING_CONTEXT_CHARS. Returns new working_context."""
    if not (text or "").strip():
        return state.working_context or ""
    new_content = (state.working_context or "").strip()
    if new_content:
        new_content += "\n" + (text or "").strip()
    else:
        new_content = (text or "").strip()
    if len(new_content) > MAX_WORKING_CONTEXT_CHARS:
        new_content = new_content[-MAX_WORKING_CONTEXT_CHARS:]
    state.working_context = new_content
    return state.working_context


def working_context_replace(state: SessionState, old_substring: str, new_substring: str) -> str:
    """Replace first occurrence of old_substring with new_substring in working context. Enforces cap. Returns new working_context."""
    current = state.working_context or ""
    if not (old_substring or "").strip():
        return current
    new_content = current.replace((old_substring or "").strip(), (new_substring or "").strip(), 1)
    if len(new_content) > MAX_WORKING_CONTEXT_CHARS:
        new_content = new_content[-MAX_WORKING_CONTEXT_CHARS:]
    state.working_context = new_content
    return state.working_context


def working_context_get(state: SessionState) -> str:
    """Return current working context (read-only)."""
    return state.working_context or ""
