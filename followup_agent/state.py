"""Follow-up state per account: harper_followup_state.json read/write."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from harper_agent.config import get_memory_root

WAITING_ON = Literal["client", "underwriter", "none"]
STATUS = Literal["active", "stopped_after_max_followups"]
STATE_FILENAME = "harper_followup_state.json"


def _account_dir(account_id: str, root: Path | None = None) -> Path:
    root = root or get_memory_root()
    return root / "objects" / "accounts" / account_id


def _state_path(account_id: str, root: Path | None = None) -> Path:
    return _account_dir(account_id, root) / STATE_FILENAME


def get_followup_state(account_id: str, root: Path | None = None) -> dict | None:
    """Load follow-up state for an account. Returns None if missing or invalid."""
    path = _state_path(account_id, root)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "account_id" in data:
            return data
        return None
    except (json.JSONDecodeError, OSError):
        return None


def set_followup_state(
    account_id: str,
    *,
    last_activity_at: str | None = None,
    last_harper_email_at: str | None = None,
    followup_count: int | None = None,
    waiting_on: WAITING_ON | None = None,
    status: STATUS | None = None,
    root: Path | None = None,
) -> dict:
    """
    Update follow-up state (merge with existing). All args are optional; only provided
    keys are updated. Returns the full state after write.
    """
    root = root or get_memory_root()
    path = _state_path(account_id, root)
    existing = get_followup_state(account_id, root) or {}
    state = {
        "account_id": account_id,
        "last_activity_at": existing.get("last_activity_at"),
        "last_harper_email_at": existing.get("last_harper_email_at"),
        "followup_count": existing.get("followup_count", 0),
        "waiting_on": existing.get("waiting_on", "none"),
        "status": existing.get("status", "active"),
    }
    if last_activity_at is not None:
        state["last_activity_at"] = last_activity_at
    if last_harper_email_at is not None:
        state["last_harper_email_at"] = last_harper_email_at
    if followup_count is not None:
        state["followup_count"] = min(2, max(0, followup_count))
    if waiting_on is not None:
        state["waiting_on"] = waiting_on
    if status is not None:
        state["status"] = status
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return state


def reset_followup_on_new_communication(
    account_id: str,
    activity_at: str,
    root: Path | None = None,
) -> dict:
    """Set followup_count = 0 and last_activity_at = activity_at (CDC reset)."""
    return set_followup_state(
        account_id,
        last_activity_at=activity_at,
        followup_count=0,
        root=root,
    )
