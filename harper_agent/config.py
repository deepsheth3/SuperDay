"""Configuration for Harper agent."""
import os
from pathlib import Path

MEMORY_ROOT = Path(os.environ.get("HARPER_MEMORY_ROOT", "memory")).resolve()

# Optional Redis for follow-up/CDC pipeline cache (TTL). If unset, pipeline runs without cache.
REDIS_URL = os.environ.get("REDIS_URL", "").strip() or None


def get_memory_root() -> Path:
    return MEMORY_ROOT
