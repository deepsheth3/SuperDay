"""Configuration for Harper agent."""
import os
from pathlib import Path

MEMORY_ROOT = Path(os.environ.get("HARPER_MEMORY_ROOT", "memory")).resolve()

# Optional Redis for follow-up/CDC pipeline cache (TTL). If unset, pipeline runs without cache.
REDIS_URL = os.environ.get("REDIS_URL", "").strip() or None

# --- Context budget and ratios (single place to tune; caps derived from these) ---
CONTEXT_BUDGET_TOKENS = 32_000
CHARS_PER_TOKEN = 4

# Ratios of context budget (0.0–1.0)
WORKING_CONTEXT_RATIO = 0.10       # Working context can use up to this share of budget (in chars)
ROLLING_SUMMARY_RATIO = 0.05       # Rolling summary cap as share of budget (converted to words)
TURN_HISTORY_RATIO = 0.15          # Turn history target share of budget (for deriving max turns)
WARNING_RATIO = 0.70               # Inject memory pressure when usage >= this share of budget
FLUSH_RATIO = 1.0                  # Evict when usage >= this share of budget
EVICT_RATIO = 0.5                  # When evicting, drop this share of oldest turns

# For deriving MAX_RECENT_TURNS: assumed average tokens per turn (user + assistant + tool output)
ESTIMATED_AVG_TOKENS_PER_TURN = 300

# Derived caps (used by session_manager and queue_manager)
def _working_context_max_chars() -> int:
    return int(CONTEXT_BUDGET_TOKENS * CHARS_PER_TOKEN * WORKING_CONTEXT_RATIO)


def _rolling_summary_max_words() -> int:
    # ~0.75 words per token
    return int(CONTEXT_BUDGET_TOKENS * ROLLING_SUMMARY_RATIO * 0.75)


def _max_recent_turns() -> int:
    n = int((CONTEXT_BUDGET_TOKENS * TURN_HISTORY_RATIO) / ESTIMATED_AVG_TOKENS_PER_TURN)
    return max(6, n)


def get_memory_root(tenant_id: str | None = None) -> Path:
    """Return memory root; if tenant_id is set, return tenant-scoped subdir (Option A)."""
    if not tenant_id or not tenant_id.strip():
        return MEMORY_ROOT
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in tenant_id.strip())
    return MEMORY_ROOT / safe
