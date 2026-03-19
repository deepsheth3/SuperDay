"""Shared shaping of session/transcript data for HTTP APIs (Flask, FastAPI)."""
from __future__ import annotations

from typing import Any

from harper_agent.session_manager import get_session


def history_turns_for_ui(session_id: str, tenant_id: str | None = None) -> list[dict[str, Any]]:
    """Match Flask /api/history: working-memory turns with tool-output truncation for assistant."""
    state = get_session(session_id, tenant_id=tenant_id)
    turns: list[dict[str, Any]] = []
    for t in state.turn_history:
        msg = t.message or ""
        if t.role == "assistant" and msg.startswith("[Tool ") and len(msg) > 280:
            msg = msg.split("\n", 1)[0] + " — [details used to form the answer below]"
        turn: dict[str, Any] = {"role": t.role, "message": msg}
        if getattr(t, "list_items", None):
            turn["list_items"] = t.list_items
        if getattr(t, "references", None):
            turn["references"] = t.references
        turns.append(turn)
    return turns
