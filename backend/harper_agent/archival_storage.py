"""Archival storage (MemGPT-style): searchable account/business memory for LLM tools.
Wraps indices + account objects; exposes search with pagination."""
from __future__ import annotations

import re
from pathlib import Path

from harper_agent.config import get_memory_root
from harper_agent.normalize import US_STATE_TO_ABBREV
from harper_agent.evidence_bundler import build_evidence_bundle_from_account_data
from harper_agent.index_navigator import navigate
from harper_agent.models import (
    EntityConstraints,
    EntityFrame,
    EntityHints,
    PrimaryEntityType,
)
from harper_agent.resolver import resolve
from harper_agent.tools import object_get_account


DEFAULT_ARCHIVAL_PAGE_SIZE = 10


def _parse_state_from_query(query: str) -> str | None:
    """If query mentions a US state (e.g. 'in Texas', 'Texas', 'CO'), return the state name or abbrev for filtering."""
    if not (query or query.strip()):
        return None
    q = " " + (query or "").strip().lower() + " "
    # Try full state names (longest first to match "new york" before "york")
    for name, abbr in sorted(US_STATE_TO_ABBREV.items(), key=lambda x: -len(x[0])):
        name_lower = name.lower()
        if re.search(r"\b" + re.escape(name_lower) + r"\b", q):
            return name_lower.title()
    # Try 2-letter codes as whole words
    for name, abbr in US_STATE_TO_ABBREV.items():
        if re.search(r"\b" + re.escape(abbr.lower()) + r"\b", q):
            return abbr.upper()
    return None


def resolve_account_id(value: str, root: Path | None = None) -> str | None:
    """Resolve a string to an account ID. Accepts either an existing acct_* ID or an account name.
    Returns the resolved account_id or None if not found or invalid.
    """
    root = root or get_memory_root()
    value = (value or "").strip()
    if not value:
        return None
    # Already looks like an account ID
    if value.lower().startswith("acct_"):
        if object_get_account(value, root) is not None:
            return value
        return None
    # Treat as account name: navigate (all accounts) + resolve by name
    hints = EntityHints(account_name=value, person_name=None)
    constraints = EntityConstraints(state=None, industry=None, status=None, city=None)
    frame = EntityFrame(
        primary_entity_type=PrimaryEntityType.ACCOUNT,
        entity_hints=hints,
        constraints=constraints,
    )
    candidate_ids, _ = navigate(frame, root)
    if not candidate_ids:
        accounts_dir = root / "objects" / "accounts"
        if accounts_dir.is_dir():
            candidate_ids = [
                d.name for d in accounts_dir.iterdir()
                if d.is_dir() and d.name.startswith("acct_")
            ]
    if not candidate_ids:
        return None
    resolved_ids, disambig, _ = resolve(frame, candidate_ids, root)
    if not resolved_ids:
        return None
    return resolved_ids[0]


def _account_summary_line(account_id: str, root: Path) -> str:
    """One-line summary for an account for search results."""
    data = object_get_account(account_id, root)
    if not data:
        return f"Account {account_id}: (no data)"
    profile = data.get("profile") or data.get("full") or {}
    name = (
        profile.get("company_name")
        or profile.get("dba_name")
        or (profile.get("structured_data") or {}).get("company_name")
        or account_id
    )
    status = (data.get("status") or {})
    if isinstance(status, dict):
        status_str = status.get("current_status") or status.get("status") or "N/A"
    else:
        status_str = "N/A"
    addr = profile.get("address") or (profile.get("structured_data") or {})
    city = addr.get("city") or (profile.get("structured_data") or {}).get("city") or ""
    state = addr.get("state") or (profile.get("structured_data") or {}).get("state") or ""
    loc = f"{city}, {state}".strip(", ")
    return f"Account {account_id}: {name} — {status_str}" + (f" — {loc}" if loc else "")


def archival_storage_search(
    query: str = "",
    *,
    state: str | None = None,
    industry: str | None = None,
    status: str | None = None,
    city: str | None = None,
    account_name: str | None = None,
    person_name: str | None = None,
    page: int = 1,
    limit: int = DEFAULT_ARCHIVAL_PAGE_SIZE,
    root: Path | None = None,
) -> tuple[list[str], int]:
    """Search archival storage (indices + account objects). Returns (formatted_snippets, total_count).
    Uses query as account_name if provided; otherwise uses filters (state, industry, status, city, person_name).
    Results are paginated; each snippet is a one-line account summary or a short evidence preview.
    """
    root = root or get_memory_root()
    # When LLM passes only query (e.g. "Which accounts are in Texas?"), derive state from query
    state_resolved = (state or "").strip() or _parse_state_from_query(query)
    # Don't use full question as account_name when we parsed a location
    name_from_query = (account_name or (query if not state_resolved else "") or "").strip() or None
    hints = EntityHints(
        account_name=account_name or name_from_query,
        person_name=(person_name or "").strip() or None,
    )
    constraints = EntityConstraints(
        state=state_resolved or None,
        industry=(industry or "").strip() or None,
        status=(status or "").strip() or None,
        city=(city or "").strip() or None,
    )
    frame = EntityFrame(
        primary_entity_type=PrimaryEntityType.ACCOUNT,
        entity_hints=hints,
        constraints=constraints,
    )
    candidate_ids, nav_error = navigate(frame, root)
    if nav_error or not candidate_ids:
        if not candidate_ids and (hints.account_name or hints.person_name):
            # Fallback: all accounts then filter by name
            accounts_dir = root / "objects" / "accounts"
            if accounts_dir.is_dir():
                candidate_ids = [
                    d.name for d in accounts_dir.iterdir()
                    if d.is_dir() and d.name.startswith("acct_")
                ]
        if not candidate_ids:
            return [], 0
    resolved_ids, disambig, _ = resolve(frame, candidate_ids, root)
    if disambig == "disambiguation" and len(resolved_ids) > 1:
        # Return all matches for search (no single resolution)
        result_ids = resolved_ids
    elif resolved_ids:
        result_ids = resolved_ids
    else:
        result_ids = candidate_ids[: limit * 5]  # cap for performance
    total = len(result_ids)
    start = (page - 1) * limit
    end = start + limit
    page_ids = result_ids[start:end]
    snippets = [_account_summary_line(aid, root) for aid in page_ids]
    return snippets, total


def archival_storage_get_evidence(
    account_id: str,
    scope: str = "full",
    *,
    root: Path | None = None,
) -> list[str]:
    """Get evidence bundle for one account as formatted text lines for LLM context.
    Scope: full, status_only, contact_only, recent_activity, minimal.
    account_id can be an acct_* ID or an account name (resolved via resolve_account_id).
    """
    root = root or get_memory_root()
    resolved = resolve_account_id(account_id, root)
    if resolved is None:
        return []
    bundle = build_evidence_bundle_from_account_data(resolved, root, scope=scope)
    lines = []
    for i, item in enumerate(bundle.items, 1):
        c = item.content
        if isinstance(c, dict):
            if "company_name" in c or "current_status" in c or "status" in c:
                lines.append(f"[{i}] {c}")
            else:
                lines.append(f"[{i}] {str(c)[:400]}")
        else:
            lines.append(f"[{i}] {str(c)[:400]}")
    return lines
