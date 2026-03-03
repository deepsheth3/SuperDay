"""Ingest harper_accounts.jsonl into memory/objects/accounts/ and indices; emit CDC events."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from harper_agent.config import get_memory_root
from harper_agent.normalize import industry_key, person_key, state_key

from followup_agent.events import append_event

# Status values from JSON are used as index keys (slugified if needed).
def _status_key(s: str) -> str:
    if not s:
        return ""
    return s.strip().lower().replace(" ", "_")


def _city_key(s: str) -> str:
    if not s:
        return ""
    return s.strip().lower().replace(" ", "_")


def write_account(
    account_id: str,
    profile: dict[str, Any],
    status_value: str,
    full: dict[str, Any],
    root: Path | None = None,
    emit_cdc: bool = True,
) -> None:
    """
    Write one account to memory/objects/accounts/<account_id>/ (profile.json, status.json, full.json).
    Update indices (location, industry, status, person). If emit_cdc is True, append
    communication_added (when emails/calls/messages present) and status_changed events.
    """
    root = root or get_memory_root()
    base = root / "objects" / "accounts" / account_id
    base.mkdir(parents=True, exist_ok=True)

    (base / "profile.json").write_text(json.dumps(profile, indent=2), encoding="utf-8")
    status_obj = {"current_status": status_value, "status": status_value}
    (base / "status.json").write_text(json.dumps(status_obj, indent=2), encoding="utf-8")
    (base / "full.json").write_text(json.dumps(full, indent=2), encoding="utf-8")

    # Indices: append this account_id to the right index files
    indices = root / "indices"
    indices.mkdir(parents=True, exist_ok=True)

    # Location: US / state / city / accounts.json
    state = (profile.get("state") or "").strip()
    city = (profile.get("city") or "").strip()
    if state and city:
        state_k = state_key(state)
        if len(state_k) == 2:
            state_k = state_k.upper()
        city_k = _city_key(city)
        loc_dir = indices / "location" / "US" / state_k / city_k
        loc_dir.mkdir(parents=True, exist_ok=True)
        acc_path = loc_dir / "accounts.json"
        _append_to_index(acc_path, account_id)

    # Industry
    ind_primary = profile.get("industry_primary") or ""
    if ind_primary:
        ik = industry_key(ind_primary)
        if ik:
            ind_dir = indices / "industry" / ik
            ind_dir.mkdir(parents=True, exist_ok=True)
            _append_to_index(ind_dir / "accounts.json", account_id)

    # Status
    sk = _status_key(status_value)
    if sk:
        status_dir = indices / "status" / sk
        status_dir.mkdir(parents=True, exist_ok=True)
        _append_to_index(status_dir / "accounts.json", account_id)

    # Person: from emails/calls contact names
    people = set()
    for e in full.get("emails") or []:
        name = (e.get("parsed_entities") or {}).get("contact_name") or e.get("from_address", "").split("@")[0]
        if name and "harper" not in name.lower():
            people.add(person_key(name))
    for c in full.get("phone_calls") or []:
        name = c.get("contact_name") or ""
        if name:
            people.add(person_key(name))
    for pk in people:
        if pk:
            person_dir = indices / "person" / pk
            person_dir.mkdir(parents=True, exist_ok=True)
            _append_to_index(person_dir / "accounts.json", account_id)

    if emit_cdc:
        has_comms = bool(
            full.get("emails") or full.get("phone_calls") or full.get("messages")
        )
        if has_comms:
            # Latest timestamp from communications for last_activity_at
            ts = ""
            for e in full.get("emails") or []:
                t = e.get("sent_at") or ""
                if t > ts:
                    ts = t
            for c in full.get("phone_calls") or []:
                t = c.get("started_at") or ""
                if t > ts:
                    ts = t
            for m in full.get("messages") or []:
                t = m.get("sent_at") or ""
                if t > ts:
                    ts = t
            append_event(
                "communication_added",
                account_id,
                {"channel": "ingest", "latest_at": ts},
                root=root,
            )
        append_event(
            "status_changed",
            account_id,
            {"new_status": status_value},
            root=root,
        )


def _append_to_index(path: Path, account_id: str) -> None:
    """Append account_id to index file (accounts.json with list account_ids)."""
    data = {"account_ids": []}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data.get("account_ids"), list):
                data["account_ids"] = []
        except (json.JSONDecodeError, OSError):
            pass
    ids = list(data["account_ids"])
    if account_id not in ids:
        ids.append(account_id)
        data["account_ids"] = ids
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def ingest_jsonl(
    path: Path | None = None,
    root: Path | None = None,
    emit_cdc: bool = True,
) -> int:
    """
    Read harper_accounts.jsonl (or path) and write each account to memory; emit CDC events.
    Returns number of accounts ingested.
    """
    root = root or get_memory_root()
    if path is None:
        path = Path(__file__).resolve().parent.parent / "harper_accounts.jsonl"
    if not path.exists():
        return 0
    count = 0
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            account_id = rec.get("account_id")
            if not account_id:
                continue
            structured = rec.get("structured_data") or {}
            profile = {**structured, "company_name": rec.get("company_name")}
            status_value = rec.get("status") or "unknown"
            full = {
                "emails": rec.get("emails") or [],
                "phone_calls": rec.get("phone_calls") or [],
                "messages": rec.get("messages") or [],
            }
            write_account(account_id, profile, status_value, full, root=root, emit_cdc=emit_cdc)
            count += 1
    return count
