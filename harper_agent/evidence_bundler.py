"""Build evidence bundle from account data for answer composition. Intent-scoped (design §15.1)."""
from __future__ import annotations

from harper_agent.config import get_memory_root
from harper_agent.constants import (
    EVIDENCE_SCOPE_CONTACT_ONLY,
    EVIDENCE_SCOPE_FULL,
    EVIDENCE_SCOPE_MINIMAL,
    EVIDENCE_SCOPE_RECENT_ACTIVITY,
    EVIDENCE_SCOPE_STATUS_ONLY,
    SOURCE_PATH_CALLS,
    SOURCE_PATH_EMAILS,
    SOURCE_PATH_PROFILE,
    SOURCE_PATH_STATUS,
)
from harper_agent.models import EvidenceBundle, EvidenceItem
from harper_agent.tools import object_get_account


def build_evidence_bundle_from_account_data(
    account_id: str,
    root=None,
    scope: str = EVIDENCE_SCOPE_FULL,
) -> EvidenceBundle:
    root = root or get_memory_root()
    data = object_get_account(account_id, root)
    if not data:
        return EvidenceBundle(items=[])
    profile = data.get("profile") or data.get("full", {})
    status = data.get("status")
    full = data.get("full", {}) or {}
    emails = full.get("emails") or []
    calls = full.get("phone_calls") or []

    if scope == EVIDENCE_SCOPE_MINIMAL:
        items = []
        if status:
            items.append(EvidenceItem(
                source_path=SOURCE_PATH_STATUS,
                source_id=account_id,
                content=status,
                timestamp="",
            ))
        if profile and not items:
            name = (profile.get("company_name") or profile.get("dba_name") or (profile.get("structured_data") or {}).get("company_name") or account_id)
            items.append(EvidenceItem(
                source_path=SOURCE_PATH_PROFILE,
                source_id=account_id,
                content={"company_name": name, "account_id": account_id},
                timestamp="",
            ))
        return EvidenceBundle(items=items)

    if scope == EVIDENCE_SCOPE_STATUS_ONLY:
        items = []
        if status:
            items.append(EvidenceItem(
                source_path=SOURCE_PATH_STATUS,
                source_id=account_id,
                content=status,
                timestamp="",
            ))
        if profile:
            items.append(EvidenceItem(
                source_path=SOURCE_PATH_PROFILE,
                source_id=account_id,
                content={"company_name": profile.get("company_name") or profile.get("dba_name"), "account_id": account_id},
                timestamp="",
            ))
        return EvidenceBundle(items=items)

    if scope == EVIDENCE_SCOPE_CONTACT_ONLY:
        items = []
        if profile:
            items.append(EvidenceItem(
                source_path=SOURCE_PATH_PROFILE,
                source_id=account_id,
                content=profile,
                timestamp="",
            ))
        for e in emails[:5]:
            items.append(EvidenceItem(
                source_path=SOURCE_PATH_EMAILS,
                source_id=e.get("id", ""),
                content=e,
                timestamp=e.get("sent_at", ""),
            ))
        for c in calls[:3]:
            items.append(EvidenceItem(
                source_path=SOURCE_PATH_CALLS,
                source_id=c.get("id", ""),
                content=c,
                timestamp=c.get("started_at", ""),
            ))
        return EvidenceBundle(items=items)

    if scope == EVIDENCE_SCOPE_RECENT_ACTIVITY:
        items = []
        if status:
            items.append(EvidenceItem(
                source_path=SOURCE_PATH_STATUS,
                source_id=account_id,
                content=status,
                timestamp="",
            ))
        for e in emails[:10]:
            items.append(EvidenceItem(
                source_path=SOURCE_PATH_EMAILS,
                source_id=e.get("id", ""),
                content=e,
                timestamp=e.get("sent_at", ""),
            ))
        for c in calls[:5]:
            items.append(EvidenceItem(
                source_path=SOURCE_PATH_CALLS,
                source_id=c.get("id", ""),
                content=c,
                timestamp=c.get("started_at", ""),
            ))
        return EvidenceBundle(items=items)

    # EVIDENCE_SCOPE_FULL (default)
    items = []
    if profile:
        items.append(EvidenceItem(
            source_path=SOURCE_PATH_PROFILE,
            source_id=account_id,
            content=profile,
            timestamp="",
        ))
    if status:
        items.append(EvidenceItem(
            source_path=SOURCE_PATH_STATUS,
            source_id=account_id,
            content=status,
            timestamp="",
        ))
    if full and full != profile:
        for e in emails[:10]:
            items.append(EvidenceItem(
                source_path=SOURCE_PATH_EMAILS,
                source_id=e.get("id", ""),
                content=e,
                timestamp=e.get("sent_at", ""),
            ))
        for c in calls[:5]:
            items.append(EvidenceItem(
                source_path=SOURCE_PATH_CALLS,
                source_id=c.get("id", ""),
                content=c,
                timestamp=c.get("started_at", ""),
            ))
    return EvidenceBundle(items=items)
