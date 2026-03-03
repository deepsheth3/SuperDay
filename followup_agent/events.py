"""CDC event store: append and read events from memory/event_store/events.jsonl."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from harper_agent.config import get_memory_root

EVENT_TYPES = ("communication_added", "status_changed")
EVENTS_FILENAME = "events.jsonl"
EMAIL_LOG_FILENAME = "email_log.jsonl"


def _event_store_root(root: Path | None = None) -> Path:
    root = root or get_memory_root()
    store = root / "event_store"
    store.mkdir(parents=True, exist_ok=True)
    return store


def append_event(
    event_type: str,
    account_id: str,
    payload: dict[str, Any] | None = None,
    root: Path | None = None,
) -> str:
    """Append a CDC event. Returns event_id."""
    if event_type not in EVENT_TYPES:
        raise ValueError(f"event_type must be one of {EVENT_TYPES}")
    store = _event_store_root(root)
    path = store / EVENTS_FILENAME
    event_id = f"evt_{uuid.uuid4().hex[:12]}"
    record = {
        "event_id": event_id,
        "event_type": event_type,
        "account_id": account_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": payload or {},
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return event_id


def read_events(
    root: Path | None = None,
    after_byte_offset: int = 0,
    limit: int = 10_000,
) -> tuple[list[dict[str, Any]], int]:
    """
    Read events from the log. Returns (list of event dicts, next_byte_offset).
    Pass after_byte_offset from a previous run to read only new events.
    """
    store = _event_store_root(root)
    path = store / EVENTS_FILENAME
    if not path.exists():
        return [], 0
    size = path.stat().st_size
    if after_byte_offset >= size:
        return [], size
    events = []
    current_offset = after_byte_offset
    with path.open("rb") as f:
        if after_byte_offset > 0:
            f.seek(after_byte_offset)
        for line in f:
            current_offset = f.tell()
            try:
                decoded = line.decode("utf-8").rstrip("\n")
            except UnicodeDecodeError:
                continue
            if not decoded:
                continue
            try:
                events.append(json.loads(decoded))
            except json.JSONDecodeError:
                continue
            if len(events) >= limit:
                break
    return events, current_offset if events else path.stat().st_size


def log_email_sent(
    account_id: str,
    email_type: str,
    outcome: str = "sent",
    root: Path | None = None,
) -> None:
    """Append to email log for idempotency/auditing (e.g. FOLLOWUP_1, FOLLOWUP_2, UPDATE)."""
    store = _event_store_root(root)
    path = store / EMAIL_LOG_FILENAME
    record = {
        "account_id": account_id,
        "email_type": email_type,
        "outcome": outcome,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
