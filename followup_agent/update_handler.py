"""Handle status_change events: send immediate update email to client and optionally set follow-up state."""
from __future__ import annotations

import logging
from pathlib import Path

from harper_agent.config import get_memory_root

logger = logging.getLogger(__name__)
from harper_agent.tools import object_get_account

from followup_agent.events import log_email_sent
from followup_agent.mailer import send_underwriter_update
from followup_agent.state import set_followup_state


def _client_email(account_id: str, root: Path) -> str | None:
    data = object_get_account(account_id, root)
    if not data:
        return None
    profile = data.get("profile") or data.get("full") or {}
    email = profile.get("preferred_contact_email") or profile.get("email")
    if email:
        return email
    full = data.get("full") or {}
    for e in full.get("emails") or []:
        addr = e.get("from_address") or (e.get("to_addresses") or [None])[0]
        if addr and "@" in str(addr) and "harper" not in str(addr).lower():
            return addr
    return None


def handle_status_changed(
    account_id: str,
    payload: dict,
    root: Path | None = None,
) -> bool:
    """
    On status_change event: send client an update email. If payload indicates client action needed,
    set waiting_on=client and followup_count=0. Returns True if email sent (or attempted).
    """
    root = root or get_memory_root()
    client_email = _client_email(account_id, root)
    if not client_email:
        return False
    new_status = payload.get("new_status") or payload.get("status") or "updated"
    status_message = f"Your quote/application status: {new_status}"
    if send_underwriter_update(account_id, client_email, status_message, payload):
        log_email_sent(account_id, "UPDATE", root=root)
        logger.info("Update handler: sent status update to %s (%s) status=%s", account_id, client_email, new_status)
        if payload.get("requires_client_action"):
            set_followup_state(
                account_id,
                waiting_on="client",
                followup_count=0,
                last_activity_at=payload.get("timestamp"),
                root=root,
            )
        return True
    return False
