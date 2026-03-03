"""CDC consumer: process events from event_store and update follow-up state (reset on new communication)."""
from __future__ import annotations

import logging
from pathlib import Path

from harper_agent.config import get_memory_root

from followup_agent.cache import get_cdc_last_offset, invalidate_followup_cache, set_cdc_last_offset
from followup_agent.events import read_events
from followup_agent.state import reset_followup_on_new_communication
from followup_agent.update_handler import handle_status_changed

logger = logging.getLogger(__name__)


def process_events(root: Path | None = None, limit: int = 5000) -> int:
    """
    Process new CDC events: for communication_added, reset follow-up state (followup_count=0, last_activity_at).
    For status_changed, send immediate client update email and invalidate cache.
    Returns number of events processed.
    """
    root = root or get_memory_root()
    offset = get_cdc_last_offset()
    if offset is None:
        offset = 0
    events, next_offset = read_events(root=root, after_byte_offset=offset, limit=limit)
    for ev in events:
        event_type = ev.get("event_type")
        account_id = ev.get("account_id")
        ts = ev.get("timestamp") or ""
        payload = ev.get("payload") or {}
        if not account_id:
            continue
        if event_type == "communication_added":
            reset_followup_on_new_communication(account_id, activity_at=ts, root=root)
            invalidate_followup_cache(account_id)
            logger.info("CDC: reset follow-up for account %s (communication_added)", account_id)
        elif event_type == "status_changed":
            sent = handle_status_changed(account_id, {**payload, "timestamp": ts}, root=root)
            invalidate_followup_cache(account_id)
            logger.info("CDC: status_changed account=%s update_email_sent=%s", account_id, sent)
    if events:
        set_cdc_last_offset(next_offset)
        logger.info("CDC: processed %d events, next_offset=%s", len(events), next_offset)
    return len(events)
