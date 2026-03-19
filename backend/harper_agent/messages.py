"""Centralized user-facing messages. No hardcoded answers in application logic."""
from __future__ import annotations

# Empty / invalid input (agent_loop)
MSG_EMPTY_QUERY = "Please ask a question about an account, contact, or status."

# Answer composer
MSG_NO_EVIDENCE = "No evidence available for this account."
MSG_NO_EVIDENCE_LINES = "No evidence."

# Fallback narrative building blocks (answer_composer)
MSG_FALLBACK_STATUS = "Current status: {status} [2]."
MSG_FALLBACK_NO_SUMMARY = "No account summary available."
MSG_FALLBACK_PRIMARY_CONTACTS = "Primary contact(s): {contacts}."
MSG_FALLBACK_RECENT_ON_RECORD = "Recent emails and calls are on record ({refs})."
