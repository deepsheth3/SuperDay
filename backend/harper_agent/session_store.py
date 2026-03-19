"""Session store interface (design §9.4). Durable file-based implementation; optional in-memory cache. Tenant-scoped."""
from __future__ import annotations

import json
from pathlib import Path

from harper_agent.config import get_memory_root
from harper_agent.models import SessionState

# Optional in-memory cache: key = (session_id, tenant_id or "")
_cache: dict[tuple[str, str], SessionState] = {}


def _sessions_dir(tenant_id: str | None = None) -> Path:
    root = get_memory_root(tenant_id)
    out = root / "sessions"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _session_path(session_id: str, tenant_id: str | None = None) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in session_id)
    if not safe:
        safe = "default"
    return _sessions_dir(tenant_id) / f"{safe}.json"


def _cache_key(session_id: str, tenant_id: str | None) -> tuple[str, str]:
    return (session_id, tenant_id or "")


def get_session(session_id: str, *, tenant_id: str | None = None) -> SessionState | None:
    """Load session by id from durable store (tenant-scoped). Returns None if not found."""
    if not session_id:
        return None
    path = _session_path(session_id, tenant_id)
    if not path.exists():
        _cache.pop(_cache_key(session_id, tenant_id), None)
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        state = SessionState.model_validate(data)
        _cache[_cache_key(session_id, tenant_id)] = state
        return state
    except (OSError, json.JSONDecodeError, ValueError):
        return _cache.get(_cache_key(session_id, tenant_id))


def save_session(session_id: str, state: SessionState) -> None:
    """Persist session to durable store (tenant-scoped via state.tenant_id). Caller sets version/updated_at."""
    if not session_id:
        return
    tenant_id = getattr(state, "tenant_id", None)
    path = _session_path(session_id, tenant_id)
    try:
        data = state.model_dump(mode="json")
        path.write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")
        _cache[_cache_key(session_id, tenant_id)] = state
    except (OSError, TypeError, ValueError):
        pass
