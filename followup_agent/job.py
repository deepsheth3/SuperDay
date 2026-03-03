"""Follow-up job: run CDC consumer, then send follow-up #1 at 3 days, #2 at 6 days (max two)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from harper_agent.config import get_memory_root

logger = logging.getLogger(__name__)
from harper_agent.tools import object_get_account

from followup_agent.cache import get_cached_followup_state, invalidate_followup_cache, set_cached_followup_state
from followup_agent.consumer import process_events
from followup_agent.events import log_email_sent
from followup_agent.mailer import send_followup_1, send_followup_2
from followup_agent.state import get_followup_state, set_followup_state
from followup_agent.waiting import get_waiting_on_client_account_ids

DAYS_FIRST_FOLLOWUP = 3
DAYS_SECOND_FOLLOWUP = 6


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        from datetime import datetime
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _client_email(account_id: str, root: Path | None) -> str | None:
    """Get primary client email from account profile/full."""
    data = object_get_account(account_id, root)
    if not data:
        return None
    profile = data.get("profile") or data.get("full") or {}
    email = profile.get("preferred_contact_email") or profile.get("email")
    if email:
        return email
    full = data.get("full") or {}
    emails = full.get("emails") or []
    for e in emails:
        addr = e.get("from_address") or (e.get("to_addresses") or [None])[0]
        if addr and "@" in str(addr) and "harper" not in str(addr).lower():
            return addr
    return None


def run_followup_job(root: Path | None = None) -> dict[str, int]:
    """
    Run CDC consumer, then for each account waiting on client with followup_count < 2,
    apply 3-day / 6-day rules and send follow-up #1 or #2. Updates state and optional email log.
    Returns {"events_processed": n, "followup_1_sent": n, "followup_2_sent": n}.
    """
    root = root or get_memory_root()
    result = {"events_processed": 0, "followup_1_sent": 0, "followup_2_sent": 0}
    result["events_processed"] = process_events(root=root)
    logger.info("Follow-up job: CDC processed %d events", result["events_processed"])

    now = datetime.now(timezone.utc)
    account_ids = get_waiting_on_client_account_ids(root=root)

    for account_id in account_ids:
        state = get_cached_followup_state(account_id)
        if state is None:
            state = get_followup_state(account_id, root)
            if state is not None:
                set_cached_followup_state(account_id, state)
        if state is None:
            state = {"followup_count": 0, "last_activity_at": None, "waiting_on": "client", "status": "active"}
        if state.get("waiting_on") != "client" and state.get("status") != "active":
            continue
        if (state.get("followup_count") or 0) >= 2:
            continue

        last_at = _parse_iso(state.get("last_activity_at"))
        if last_at is None:
            last_at = now - timedelta(days=DAYS_FIRST_FOLLOWUP + 1)
        days_inactive = (now - last_at).total_seconds() / 86400
        count = state.get("followup_count", 0)
        client_email = _client_email(account_id, root)
        if not client_email:
            continue

        context = {"account_id": account_id, "company_name": ""}
        acc = object_get_account(account_id, root)
        if acc:
            profile = acc.get("profile") or acc.get("full") or {}
            context["company_name"] = profile.get("company_name") or profile.get("dba_name") or account_id

        if count == 0 and days_inactive >= DAYS_FIRST_FOLLOWUP:
            if send_followup_1(account_id, client_email, context):
                set_followup_state(
                    account_id,
                    followup_count=1,
                    last_harper_email_at=now.isoformat(),
                    root=root,
                )
                log_email_sent(account_id, "FOLLOWUP_1", root=root)
                invalidate_followup_cache(account_id)
                result["followup_1_sent"] += 1
                logger.info("Follow-up job: sent FOLLOWUP_1 to %s (%s)", account_id, client_email)
        elif count == 1 and days_inactive >= DAYS_SECOND_FOLLOWUP:
            if send_followup_2(account_id, client_email, context):
                set_followup_state(
                    account_id,
                    followup_count=2,
                    last_harper_email_at=now.isoformat(),
                    status="stopped_after_max_followups",
                    root=root,
                )
                log_email_sent(account_id, "FOLLOWUP_2", root=root)
                invalidate_followup_cache(account_id)
                result["followup_2_sent"] += 1
                logger.info("Follow-up job: sent FOLLOWUP_2 to %s (%s)", account_id, client_email)

    logger.info("Follow-up job done: followup_1_sent=%d followup_2_sent=%d", result["followup_1_sent"], result["followup_2_sent"])
    return result
