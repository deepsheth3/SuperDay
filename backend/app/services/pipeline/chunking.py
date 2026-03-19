"""Naive text chunking for normalize worker (replace with tokenizer-based later)."""

from __future__ import annotations

import hashlib


def chunk_text(text: str, max_chars: int = 512) -> list[str]:
    t = (text or "").strip()
    if not t:
        return []
    if len(t) <= max_chars:
        return [t]
    parts: list[str] = []
    start = 0
    while start < len(t):
        end = min(start + max_chars, len(t))
        chunk = t[start:end]
        # try break on paragraph
        if end < len(t):
            nl = chunk.rfind("\n\n")
            if nl > max_chars // 4:
                chunk = chunk[:nl].strip()
                end = start + nl
        parts.append(chunk.strip())
        start = end if end > start else start + max_chars
    return [p for p in parts if p]


def chunk_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:64]
