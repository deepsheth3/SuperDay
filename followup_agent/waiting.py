"""Resolve account IDs that are 'waiting on client' (from status indices or fallback scan)."""
from __future__ import annotations

import json
from pathlib import Path

from harper_agent.config import get_memory_root

# Status keys that mean Harper is waiting on the client (e.g. documents, reply).
WAITING_ON_CLIENT_STATUSES = ("awaiting_documents", "contacted_by_harper", "application_submitted")


def _read_account_ids(path: Path) -> list[str]:
    if not path.exists() or not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        ids = data.get("account_ids") or []
        return ids if isinstance(ids, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def get_waiting_on_client_account_ids(root: Path | None = None, refresh_cache: bool = True) -> list[str]:
    """
    Return list of account IDs that are in a 'waiting on client' status.
    Scans status indices (and fallback account status.json). If refresh_cache is True and Redis
    is configured, stores result in Redis with TTL for faster subsequent reads.
    """
    from followup_agent.cache import set_waiting_on_client_account_ids as set_cached

    root = root or get_memory_root()
    indices = root / "indices" / "status"
    account_ids = set()
    if indices.is_dir():
        for key in WAITING_ON_CLIENT_STATUSES:
            path = indices / key / "accounts.json"
            account_ids.update(_read_account_ids(path))
    if not account_ids:
        # Fallback: scan objects/accounts and check status.json
        accounts_dir = root / "objects" / "accounts"
        if accounts_dir.is_dir():
            for d in accounts_dir.iterdir():
                if not d.is_dir() or not d.name.startswith("acct_"):
                    continue
                st_path = d / "status.json"
                if not st_path.exists():
                    continue
                try:
                    data = json.loads(st_path.read_text(encoding="utf-8"))
                    status = (data.get("current_status") or data.get("status") or "").strip().lower().replace(" ", "_")
                    if status in WAITING_ON_CLIENT_STATUSES:
                        account_ids.add(d.name)
                except (json.JSONDecodeError, OSError, AttributeError):
                    pass
    result = sorted(account_ids)
    if refresh_cache:
        set_cached(result)
    return result
