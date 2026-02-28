"""Resolve candidate account IDs by name hint."""
from __future__ import annotations

import json
import re
from pathlib import Path

from harper_agent.config import get_memory_root
from harper_agent.models import EntityFrame


def _normalize_name(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"[^\w\s]", "", s.lower()).strip()
    return re.sub(r"\s+", " ", s)


def _account_matches_hint(account_id: str, account_name_hint: str, root: Path) -> bool:
    profile_path = root / "objects" / "accounts" / account_id / "profile.json"
    if not profile_path.exists():
        return False
    try:
        data = json.loads(profile_path.read_text(encoding="utf-8"))
        name = (data.get("company_name") or data.get("dba_name") or data.get("legal_name") or "")
        name_n = _normalize_name(name)
        hint_n = _normalize_name(account_name_hint)
        if not hint_n:
            return True
        return hint_n in name_n or name_n in hint_n
    except (OSError, json.JSONDecodeError):
        return False


def resolve(
    frame: EntityFrame,
    candidate_ids: list[str],
    root: Path | None = None,
) -> tuple[list[str], str | None]:
    root = root or get_memory_root()
    hint = (frame.entity_hints.account_name or "").strip()
    if not hint:
        return candidate_ids, None
    matched = [aid for aid in candidate_ids if _account_matches_hint(aid, hint, root)]
    if not matched:
        return [], None
    if len(matched) > 1:
        return matched, "disambiguation"
    return matched, None
