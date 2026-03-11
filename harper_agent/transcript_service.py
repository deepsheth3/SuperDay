"""Durable transcript store for replay, audit, and analytics. Separate from session working memory."""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from harper_agent.config import get_memory_root


def _transcript_root(root: Path | None = None) -> Path:
    root = root or get_memory_root()
    out = root / "transcripts"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _session_path(session_id: str, root: Path | None = None) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in session_id)
    return _transcript_root(root) / f"{safe}.jsonl"


def append_turn(
    session_id: str,
    role: str,
    content: str,
    *,
    turn_id: str | None = None,
    timestamp: str | None = None,
    citations: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
    tenant_id: str | None = None,
    root: Path | None = None,
) -> None:
    """Append one turn (user or assistant message) to the session transcript. Thread-safe append."""
    turn_id = turn_id or str(uuid.uuid4())
    timestamp = timestamp or datetime.now(tz=timezone.utc).isoformat()
    row = {
        "session_id": session_id,
        "turn_id": turn_id,
        "role": role,
        "content": content,
        "timestamp": timestamp,
        "citations": citations,
        "metadata": metadata or {},
        "tenant_id": tenant_id,
    }
    path = _session_path(session_id, root)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def append_turn_async(
    session_id: str,
    role: str,
    content: str,
    *,
    turn_id: str | None = None,
    timestamp: str | None = None,
    citations: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
    tenant_id: str | None = None,
    root: Path | None = None,
) -> None:
    """Fire-and-forget append so response is not blocked (design §11.1 Step 10)."""
    def _run() -> None:
        try:
            append_turn(
                session_id,
                role,
                content,
                turn_id=turn_id,
                timestamp=timestamp,
                citations=citations,
                metadata=metadata,
                tenant_id=tenant_id,
                root=root,
            )
        except Exception:
            pass

    t = threading.Thread(target=_run, daemon=True)
    t.start()


def persist_exchange_async(
    session_id: str,
    user_message: str,
    assistant_content: str,
    *,
    references: list[dict[str, Any]] | None = None,
    list_items: list[str] | None = None,
    tenant_id: str | None = None,
    root: Path | None = None,
) -> None:
    """Fire-and-forget persist of one user/assistant exchange for replay and audit."""
    def _run() -> None:
        try:
            ts = datetime.now(tz=timezone.utc).isoformat()
            turn_id = str(uuid.uuid4())
            append_turn(
                session_id,
                "user",
                user_message,
                turn_id=turn_id,
                timestamp=ts,
                tenant_id=tenant_id,
                root=root,
            )
            append_turn(
                session_id,
                "assistant",
                assistant_content,
                turn_id=str(uuid.uuid4()),
                timestamp=ts,
                citations=references,
                metadata={"list_items": list_items} if list_items else {},
                tenant_id=tenant_id,
                root=root,
            )
        except Exception:
            pass

    t = threading.Thread(target=_run, daemon=True)
    t.start()


def get_transcript(
    session_id: str,
    *,
    limit: int | None = None,
    tenant_id: str | None = None,
    root: Path | None = None,
) -> list[dict[str, Any]]:
    """Read transcript for a session (for UI replay, resume past conversation). Optional tenant filter."""
    path = _session_path(session_id, root)
    if not path.exists():
        return []
    turns = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                if tenant_id is not None and row.get("tenant_id") != tenant_id:
                    continue
                turns.append(row)
            except json.JSONDecodeError:
                continue
    if limit is not None:
        turns = turns[-limit:]
    return turns


# --- Recall storage (MemGPT-style): searchable message history for LLM tools ---

DEFAULT_RECALL_PAGE_SIZE = 10


def recall_storage_search(
    session_id: str,
    query: str = "",
    *,
    page: int = 1,
    limit: int = DEFAULT_RECALL_PAGE_SIZE,
    tenant_id: str | None = None,
    root: Path | None = None,
) -> tuple[list[str], int]:
    """Search recall storage (transcript) for a session. Returns (formatted_snippets, total_count).
    If query is empty, returns recent turns in reverse chronological order (newest first), paginated.
    Otherwise filters turns whose content contains query (case-insensitive substring).
    Snippets are formatted as: '[timestamp] role: content_preview...'
    """
    turns = get_transcript(session_id, tenant_id=tenant_id, root=root)
    if not turns:
        return [], 0
    query_lower = (query or "").strip().lower()
    if query_lower:
        matching = [
            t for t in turns
            if query_lower in (t.get("content") or "").lower()
        ]
    else:
        matching = list(turns)
    total = len(matching)
    # Reverse so newest first; then paginate
    matching = list(reversed(matching))
    start = (page - 1) * limit
    end = start + limit
    page_turns = matching[start:end]
    snippets = []
    for t in page_turns:
        ts = t.get("timestamp", "")[:19] if t.get("timestamp") else ""
        role = t.get("role", "unknown")
        content = (t.get("content") or "")[:500]
        if len((t.get("content") or "")) > 500:
            content += "..."
        snippets.append(f"[{ts}] {role}: {content}")
    return snippets, total
