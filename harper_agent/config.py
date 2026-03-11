"""Configuration for Harper agent."""
import os
from pathlib import Path

MEMORY_ROOT = Path(os.environ.get("HARPER_MEMORY_ROOT", "memory")).resolve()

# Optional Redis for follow-up/CDC pipeline cache (TTL). If unset, pipeline runs without cache.
REDIS_URL = os.environ.get("REDIS_URL", "").strip() or None


def get_memory_root(tenant_id: str | None = None) -> Path:
    """Return memory root; if tenant_id is set, return tenant-scoped subdir (Option A)."""
    if not tenant_id or not tenant_id.strip():
        return MEMORY_ROOT
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in tenant_id.strip())
    return MEMORY_ROOT / safe
