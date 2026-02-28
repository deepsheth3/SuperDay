"""Object access for account data."""
from __future__ import annotations

import json
from pathlib import Path

from harper_agent.config import get_memory_root


def object_get_account(account_id: str, root: Path | None = None) -> dict | None:
    root = root or get_memory_root()
    base = root / "objects" / "accounts" / account_id
    if not base.is_dir():
        return None
    out = {}
    for name in ("profile.json", "status.json", "full.json"):
        p = base / name
        if p.exists():
            try:
                out[name.replace(".json", "")] = json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
    return out if out else None
