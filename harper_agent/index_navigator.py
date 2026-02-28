"""Navigate multi-index memory by EntityFrame constraints."""
from __future__ import annotations

import json
from pathlib import Path

from harper_agent.models import EntityFrame, PrimaryEntityType


def _read_account_ids(path: Path) -> list[str]:
    if not path.exists() or not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        ids = data.get("account_ids") or []
        return ids if isinstance(ids, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _get_all_account_ids(root: Path) -> list[str]:
    accounts_dir = root / "objects" / "accounts"
    if not accounts_dir.is_dir():
        return []
    return [d.name for d in accounts_dir.iterdir() if d.is_dir() and d.name.startswith("acct_")]


def _intersect(sets: list[list[str]]) -> list[str]:
    if not sets:
        return []
    out = set(sets[0])
    for s in sets[1:]:
        out &= set(s)
    return sorted(out)


def navigate(frame: EntityFrame, root: Path | None = None) -> tuple[list[str], str | None]:
    from harper_agent.config import get_memory_root

    root = root or get_memory_root()
    indices = root / "indices"
    if not indices.is_dir():
        if frame.primary_entity_type in (PrimaryEntityType.ACCOUNT, PrimaryEntityType.UNKNOWN) and frame.entity_hints.account_name:
            return _get_all_account_ids(root), None
        return [], None

    candidates: list[list[str]] = []
    # Location: indices/location/US/{state}/{city}/accounts.json
    if frame.constraints.state or frame.constraints.city:
        state = (frame.constraints.state or "").strip().upper() or None
        city = (frame.constraints.city or "").strip().lower().replace(" ", "_") or None
        loc = indices / "location" / "US"
        if loc.is_dir():
            if state:
                state_dir = loc / state
                if not state_dir.is_dir():
                    for d in loc.iterdir():
                        if d.is_dir() and d.name.upper() == state:
                            state_dir = d
                            break
                if state_dir.is_dir():
                    if city:
                        city_file = state_dir / city / "accounts.json"
                        ids = _read_account_ids(city_file)
                        if ids:
                            candidates.append(ids)
                    else:
                        # State only: union of all cities in that state
                        state_ids = []
                        for sub in state_dir.iterdir():
                            if sub.is_dir():
                                ids = _read_account_ids(sub / "accounts.json")
                                state_ids.extend(ids)
                        if state_ids:
                            candidates.append(list(dict.fromkeys(state_ids)))
            if not candidates and city:
                # City only: union accounts from any state that has this city
                city_ids = []
                for state_dir in loc.iterdir():
                    if state_dir.is_dir():
                        city_file = state_dir / city / "accounts.json"
                        ids = _read_account_ids(city_file)
                        city_ids.extend(ids)
                if city_ids:
                    candidates.append(list(dict.fromkeys(city_ids)))

    # Industry
    if frame.constraints.industry:
        ind_path = indices / "industry" / frame.constraints.industry / "accounts.json"
        ids = _read_account_ids(ind_path)
        if ids:
            candidates.append(ids)

    # Status
    if frame.constraints.status:
        status_path = indices / "status" / frame.constraints.status / "accounts.json"
        ids = _read_account_ids(status_path)
        if ids:
            candidates.append(ids)

    # Person (index uses underscores, person_key uses slugify -> replace - with _)
    if frame.entity_hints.person_name:
        from harper_agent.normalize import person_key
        pk = person_key(frame.entity_hints.person_name).replace("-", "_")
        if pk:
            person_path = indices / "person" / pk / "accounts.json"
            ids = _read_account_ids(person_path)
            if ids:
                candidates.append(ids)

    if not candidates:
        if frame.primary_entity_type in (PrimaryEntityType.ACCOUNT, PrimaryEntityType.UNKNOWN) and frame.entity_hints.account_name:
            all_ids = _get_all_account_ids(root)
            if all_ids:
                return all_ids, None
        return [], None

    return _intersect(candidates), None
