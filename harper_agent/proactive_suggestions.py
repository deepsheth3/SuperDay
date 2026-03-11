"""Rule-based proactive follow-up suggestions after an answer."""
from __future__ import annotations

from harper_agent.constants import (
    SOURCE_PATH_CALLS,
    SOURCE_PATH_EMAILS,
    SOURCE_PATH_PROFILE,
    SOURCE_PATH_STATUS,
    WAITING_ON_CLIENT_STATUSES,
    normalize_status_key,
)
from harper_agent.models import EvidenceBundle

FOLLOWUP_REMINDER = "I can suggest a follow-up reminder."
LATEST_EMAIL_OR_CALL = "Want to see the latest email or call?"
MAIN_CONTACT = "Want to know who the main contact is?"


def suggest_follow_ups(
    bundle: EvidenceBundle,
    account_id: str,
    root=None,
    session_goal: str | None = None,
) -> list[str]:
    """Return 1-3 short suggested follow-up questions based on bundle and account. No LLM. Reorders by session_goal when set."""
    has_emails_or_calls = False
    status_value: str | None = None
    has_profile = False

    for item in (bundle.items or []):
        path = (item.source_path or "").strip()
        if SOURCE_PATH_EMAILS in path or SOURCE_PATH_CALLS in path:
            has_emails_or_calls = True
        if path == SOURCE_PATH_STATUS and isinstance(item.content, dict):
            status_value = (
                item.content.get("current_status")
                or item.content.get("status")
                or (item.content.get("status_key") if isinstance(item.content.get("status_key"), str) else None)
            )
        if path == SOURCE_PATH_PROFILE:
            has_profile = True

    suggestions: list[str] = []
    if has_emails_or_calls:
        suggestions.append(LATEST_EMAIL_OR_CALL)
    if status_value and normalize_status_key(status_value) in WAITING_ON_CLIENT_STATUSES:
        suggestions.append(FOLLOWUP_REMINDER)
    if has_profile:
        suggestions.append(MAIN_CONTACT)

    # Reorder by session goal so the most relevant suggestion is first
    if session_goal == "checking_follow_ups" and FOLLOWUP_REMINDER in suggestions:
        suggestions = [FOLLOWUP_REMINDER] + [s for s in suggestions if s != FOLLOWUP_REMINDER]
    elif session_goal == "preparing_outreach":
        priority = [MAIN_CONTACT, LATEST_EMAIL_OR_CALL, FOLLOWUP_REMINDER]
        suggestions = [s for s in priority if s in suggestions] + [s for s in suggestions if s not in priority]
    elif session_goal == "triaging_pipeline" and FOLLOWUP_REMINDER in suggestions:
        suggestions = [FOLLOWUP_REMINDER] + [s for s in suggestions if s != FOLLOWUP_REMINDER]

    return suggestions[:3]
