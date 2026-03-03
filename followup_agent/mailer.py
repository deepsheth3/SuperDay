"""Harper mailer: follow-up and update emails (stub; plug in real SMTP/SendGrid later)."""
from __future__ import annotations

from typing import Any


def send_followup_1(account_id: str, client_email: str, context: dict[str, Any]) -> bool:
    """Send first follow-up (3-day). Returns True if sent (or stub success)."""
    # TODO: real email send
    return True


def send_followup_2(account_id: str, client_email: str, context: dict[str, Any]) -> bool:
    """Send second follow-up (6-day). Returns True if sent (or stub success)."""
    # TODO: real email send
    return True


def send_underwriter_update(
    account_id: str,
    client_email: str,
    status_message: str,
    payload: dict[str, Any],
) -> bool:
    """Send immediate update when underwriter/quote status changes. Returns True if sent."""
    # TODO: real email send
    return True
