"""
Canonical S3 key layout (structured object storage — not primary DB).

Full key = `{s3_raw_prefix}{relative_path}` where `s3_raw_prefix` is an optional
environment root (e.g. `prod/`). Relative paths always start with `tenants/{tenant_id}/`.

See: docs/S3_KEY_LAYOUT.md
"""

from __future__ import annotations

import re
from uuid import UUID


def sanitize_path_segment(value: str, *, max_len: int = 200) -> str:
    """Safe single path segment (no slashes)."""
    s = (value or "").strip()
    if not s:
        return "unknown"
    out = "".join(c if c.isalnum() or c in "-_." else "_" for c in s)
    return out[:max_len] or "unknown"


def _tenant_segment(tenant_id: str) -> str:
    s = tenant_id.strip()
    try:
        UUID(s)
        return s.lower()
    except ValueError:
        return sanitize_path_segment(s, max_len=64)


def raw_ingest_payload_key(tenant_id: str, source_system: str, source_event_id: str) -> str:
    """
    Raw JSON (or text) captured at ingest time.

    tenants/{tenant}/raw/ingest/{source_system}/{source_event_id}/payload.json
    """
    t = _tenant_segment(tenant_id)
    src = sanitize_path_segment(source_system, max_len=80)
    evt = sanitize_path_segment(source_event_id, max_len=200)
    return f"tenants/{t}/raw/ingest/{src}/{evt}/payload.json"


def communication_body_key(tenant_id: str, communication_id: str, *, suffix: str = "body.json") -> str:
    """Normalized or clean body text linked to a communication row (metadata lives in DB)."""
    t = _tenant_segment(tenant_id)
    cid = sanitize_path_segment(communication_id, max_len=128)
    safe_suffix = re.sub(r"[^a-zA-Z0-9._-]", "_", suffix) or "body.json"
    return f"tenants/{t}/communications/{cid}/{safe_suffix}"


def attachment_key(tenant_id: str, communication_id: str, attachment_id: str, filename: str) -> str:
    """Binary attachment; `filename` is sanitized to a single segment."""
    t = _tenant_segment(tenant_id)
    cid = sanitize_path_segment(communication_id, max_len=128)
    aid = sanitize_path_segment(attachment_id, max_len=128)
    fn = sanitize_path_segment(filename, max_len=180)
    return f"tenants/{t}/communications/{cid}/attachments/{aid}/{fn}"


def archive_export_key(tenant_id: str, period: str, export_id: str) -> str:
    """Batch exports / compliance snapshots (e.g. period `2025-03`)."""
    t = _tenant_segment(tenant_id)
    per = sanitize_path_segment(period, max_len=32)
    eid = sanitize_path_segment(export_id, max_len=128)
    return f"tenants/{t}/archive/exports/{per}/{eid}.jsonl"


def join_with_prefix(prefix: str, relative_key: str) -> str:
    """Prepend optional bucket root prefix (e.g. `prod/`)."""
    p = (prefix or "").strip().strip("/")
    r = relative_key.strip().lstrip("/")
    if p:
        return f"{p}/{r}"
    return r
