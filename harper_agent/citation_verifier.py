"""Verify that narrative citations refer to evidence bundle sources."""
from __future__ import annotations

import re

from harper_agent.models import ComposedAnswer, EvidenceBundle


def verify_citations(answer: ComposedAnswer, bundle: EvidenceBundle) -> bool:
    narrative = answer.narrative or ""
    source_ids = set()
    for item in bundle.items:
        if item.source_id:
            source_ids.add(item.source_id)
        if item.source_path:
            source_ids.add(item.source_path)
    # Match [1], [1, 2], [3-9], [email_001], etc.
    for m in re.finditer(r"\[([^\]]+)\]", narrative):
        ref = m.group(1).strip()
        if ref.isdigit():
            continue
        if ref in source_ids:
            continue
        if any(ref in sid or sid in ref for sid in source_ids):
            continue
        # Comma-separated numbers or ranges (e.g. "1, 2", "3-9") refer to evidence indices
        if all(p.strip().isdigit() for p in ref.split(",")) or ("-" in ref and ref.replace(" ", "").replace("-", "").isdigit()):
            continue
        return False
    return True
