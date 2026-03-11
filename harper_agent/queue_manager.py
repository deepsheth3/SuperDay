"""MemGPT-style queue manager: token budget, memory pressure warning, eviction to free context."""
from __future__ import annotations

from harper_agent.models import SessionState, TurnRecord
from harper_agent.session_manager import MAX_ROLLING_SUMMARY_WORDS

# Context window budget (tokens). Heuristic: ~4 chars per token.
DEFAULT_MAX_CONTEXT_TOKENS = 8000
WARNING_RATIO = 0.7   # Inject memory pressure when usage >= this
FLUSH_RATIO = 1.0     # Evict when usage >= this
EVICT_RATIO = 0.5     # When evicting, drop oldest 50% of queue


def estimate_tokens(text: str) -> int:
    """Estimate token count from character count (~4 chars per token)."""
    return max(0, len((text or "").strip())) // 4


def context_token_estimate(
    system_prompt: str,
    working_context: str,
    turn_history: list[TurnRecord],
) -> int:
    """Estimate total tokens for main context (system + working + FIFO)."""
    sys_tokens = estimate_tokens(system_prompt)
    work_tokens = estimate_tokens(working_context)
    fifo_parts = []
    for t in turn_history:
        fifo_parts.append(f"{t.role}: {t.message or ''}")
        if getattr(t, "list_items", None):
            fifo_parts.append(" ".join(str(x) for x in t.list_items))
    fifo_tokens = estimate_tokens("\n".join(fifo_parts))
    return sys_tokens + work_tokens + fifo_tokens


MEMORY_PRESSURE_MESSAGE = (
    "System: Memory pressure — context is nearly full. "
    "Consider moving important facts to working context or summarizing before continuing."
)


def should_inject_memory_pressure(
    state: SessionState,
    system_prompt: str,
    max_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS,
) -> bool:
    """True if context is at or above WARNING_RATIO and we should inject a memory pressure message."""
    usage = context_token_estimate(
        system_prompt,
        state.working_context or "",
        state.turn_history,
    )
    return usage >= int(max_tokens * WARNING_RATIO)


def should_evict(
    state: SessionState,
    system_prompt: str,
    max_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS,
) -> bool:
    """True if context is at or above FLUSH_RATIO and we should evict oldest messages."""
    usage = context_token_estimate(
        system_prompt,
        state.working_context or "",
        state.turn_history,
    )
    return usage >= int(max_tokens * FLUSH_RATIO)


def _update_rolling_summary_after_evict(
    state: SessionState,
    dropped_turns: list[TurnRecord],
) -> None:
    """Merge summary of dropped turns into rolling_summary and cap at MAX_ROLLING_SUMMARY_WORDS."""
    if not dropped_turns:
        return
    parts = []
    for t in dropped_turns:
        if t.resolved_account_id:
            parts.append(f"discussed account {t.resolved_account_id}")
        if t.resolved_person_id:
            parts.append(f"mentioned person {t.resolved_person_id}")
        if t.role == "user" and t.message and not t.resolved_account_id:
            short = (t.message[:60] + "…") if len(t.message) > 60 else t.message
            parts.append(f"user asked: {short}")
    if not parts:
        parts.append("earlier turns in session")
    new_bit = " ".join(parts)
    if state.rolling_summary:
        state.rolling_summary = state.rolling_summary.strip() + " | " + new_bit
    else:
        state.rolling_summary = new_bit
    words = state.rolling_summary.split()
    if len(words) > MAX_ROLLING_SUMMARY_WORDS:
        state.rolling_summary = " ".join(words[-MAX_ROLLING_SUMMARY_WORDS:])


def evict_oldest_messages(
    state: SessionState,
    *,
    system_prompt: str = "",
    max_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS,
) -> list[TurnRecord]:
    """If over budget, evict oldest EVICT_RATIO of turn_history; update rolling_summary. Returns evicted turns.
    Evicted messages are already in recall (transcript) from normal persistence; we only trim in-memory FIFO.
    """
    if not should_evict(state, system_prompt, max_tokens):
        return []
    n = len(state.turn_history)
    if n <= 1:
        return []
    evict_count = max(1, int(n * EVICT_RATIO))
    dropped = state.turn_history[:evict_count]
    state.turn_history = state.turn_history[evict_count:]
    _update_rolling_summary_after_evict(state, dropped)
    return dropped
