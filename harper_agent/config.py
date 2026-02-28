"""Configuration for Harper agent."""
import os
from pathlib import Path

MEMORY_ROOT = Path(os.environ.get("HARPER_MEMORY_ROOT", "memory")).resolve()


def get_memory_root() -> Path:
    return MEMORY_ROOT
