"""Single source of truth for paths, intents, session goals, and status semantics. No query-specific logic."""
from __future__ import annotations

import json
from pathlib import Path

from harper_agent.config import get_memory_root

# Evidence source path constants (used by evidence_bundler, main, proactive_suggestions)
SOURCE_PATH_PROFILE = "account/profile"
SOURCE_PATH_STATUS = "account/status"
SOURCE_PATH_EMAILS = "account/emails"
SOURCE_PATH_CALLS = "account/calls"

# Intent values returned by entity extractor; validation and prompt building use these
INTENT_VALUES = frozenset({
    "status_query",
    "list_accounts",
    "follow_up",
    "compare_accounts",
    "summarize_activity",
    "suggest_next_action",
    "unknown",
})

# Session goal values (used by session_manager, entity_extractor)
ALLOWED_SESSION_GOALS = frozenset({
    "reviewing_one_account",
    "triaging_pipeline",
    "checking_follow_ups",
    "preparing_outreach",
})

# Status keys: exact membership only, no substring checks. Normalize with normalize_status_key() before lookup.
_DEFAULT_WAITING_ON_CLIENT = frozenset({
    "awaiting_documents",
    "contacted_by_harper",
    "application_submitted",
})
_DEFAULT_CONFIRM_NEXT_STEPS = frozenset({
    "quote_received",
    "quote_submitted",
    "underwriter_review",
})
_DEFAULT_CONFIRM_BINDING = frozenset({
    "policy_bound",
    "bound",
})

_CONFIG_CACHE: dict[str, frozenset[str]] | None = None


def _load_status_semantics(root: Path | None) -> dict[str, frozenset[str]]:
    """Load status sets from memory/config/status_semantics.json if present; else return defaults."""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE
    root = root or get_memory_root()
    path = root / "config" / "status_semantics.json"
    result = {
        "waiting_on_client": _DEFAULT_WAITING_ON_CLIENT,
        "confirm_next_steps": _DEFAULT_CONFIRM_NEXT_STEPS,
        "confirm_binding": _DEFAULT_CONFIRM_BINDING,
    }
    if path.exists() and path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for key, val in data.items():
                    if isinstance(val, list) and key in result:
                        result[key] = frozenset(str(v).strip().lower().replace(" ", "_") for v in val if v)
        except (json.JSONDecodeError, OSError):
            pass
    _CONFIG_CACHE = result
    return result


def get_waiting_on_client_statuses(root: Path | None = None) -> frozenset[str]:
    return _load_status_semantics(root)["waiting_on_client"]


def get_confirm_next_steps_statuses(root: Path | None = None) -> frozenset[str]:
    return _load_status_semantics(root)["confirm_next_steps"]


def get_confirm_binding_statuses(root: Path | None = None) -> frozenset[str]:
    return _load_status_semantics(root)["confirm_binding"]


# Convenience: use default sets when root is not available (e.g. in followup_agent)
WAITING_ON_CLIENT_STATUSES = _DEFAULT_WAITING_ON_CLIENT
CONFIRM_NEXT_STEPS_STATUSES = _DEFAULT_CONFIRM_NEXT_STEPS
CONFIRM_BINDING_STATUSES = _DEFAULT_CONFIRM_BINDING


def normalize_status_key(status: str | None) -> str:
    """Normalize status for membership checks: lower, spaces to underscores."""
    if status is None:
        return ""
    return (status or "").strip().lower().replace(" ", "_")
