"""
HTTP entry to the **reactive** `harper_agent` (synchronous chat path).

Adds `backend/` to `sys.path` and sets `HARPER_MEMORY_ROOT` to the repo `memory/` tree:
domain knowledge (`objects/`, `indices/`) and agent runtime state (`sessions/`, `transcripts/`).
See `docs/ARCHITECTURE.md` (terminology + source-of-truth boundaries).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _repo_root() -> Path:
    """SuperDay repository root (parent of `backend/`)."""
    return Path(__file__).resolve().parents[3]


def prepare_harper_env() -> Path:
    cs = _backend_root()
    p = str(cs)
    if p not in sys.path:
        sys.path.insert(0, p)
    repo = _repo_root()
    mem = repo / "memory"
    if mem.is_dir():
        os.environ.setdefault("HARPER_MEMORY_ROOT", str(mem))
    else:
        os.environ.setdefault("HARPER_MEMORY_ROOT", str(mem))
    return repo


_ensure_path_and_memory_env = prepare_harper_env


def sync_run_chat(
    session_id: str | None,
    message: str,
    goal: str | None,
    tenant_id: str | None,
    trace_id: str,
    request_id: str,
) -> dict[str, Any]:
    prepare_harper_env()
    from harper_agent.main import run_agent_loop
    from harper_agent.session_manager import create_session_id

    sid = session_id or create_session_id()
    result = run_agent_loop(
        sid,
        message,
        goal=goal,
        tenant_id=tenant_id,
        trace_id=trace_id,
        request_id=request_id or None,
    )
    out: dict[str, Any] = {
        "reply": result["narrative"],
        "session_id": sid,
        "request_id": request_id,
    }
    if result.get("list_items"):
        out["list_items"] = result["list_items"]
    if result.get("references"):
        out["references"] = result["references"]
    if result.get("suggested_follow_ups"):
        out["suggested_follow_ups"] = result["suggested_follow_ups"]
    return out


def sync_history_turns(session_id: str, tenant_id: str | None) -> list[dict[str, Any]]:
    prepare_harper_env()
    from harper_agent.ui_adapters import history_turns_for_ui

    return history_turns_for_ui(session_id, tenant_id=tenant_id)


def sync_get_transcript(session_id: str, tenant_id: str | None) -> list[dict[str, Any]]:
    prepare_harper_env()
    from harper_agent.transcript_service import get_transcript

    return get_transcript(session_id, tenant_id=tenant_id)
