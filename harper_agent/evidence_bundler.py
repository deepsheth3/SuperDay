"""Build evidence bundle from account data for answer composition."""
from __future__ import annotations

from harper_agent.config import get_memory_root
from harper_agent.models import EvidenceBundle, EvidenceItem
from harper_agent.tools import object_get_account


def build_evidence_bundle_from_account_data(
    account_id: str,
    root=None,
) -> EvidenceBundle:
    root = root or get_memory_root()
    data = object_get_account(account_id, root)
    if not data:
        return EvidenceBundle(items=[])
    items = []
    profile = data.get("profile") or data.get("full", {})
    if profile:
        items.append(EvidenceItem(
            source_path="account/profile",
            source_id=account_id,
            content=profile,
            timestamp="",
        ))
    status = data.get("status")
    if status:
        items.append(EvidenceItem(
            source_path="account/status",
            source_id=account_id,
            content=status,
            timestamp="",
        ))
    full = data.get("full", {})
    if full and full != profile:
        emails = full.get("emails") or []
        for e in emails[:10]:
            items.append(EvidenceItem(
                source_path="account/emails",
                source_id=e.get("id", ""),
                content=e,
                timestamp=e.get("sent_at", ""),
            ))
        for c in (full.get("phone_calls") or [])[:5]:
            items.append(EvidenceItem(
                source_path="account/calls",
                source_id=c.get("id", ""),
                content=c,
                timestamp=c.get("started_at", ""),
            ))
    return EvidenceBundle(items=items)
