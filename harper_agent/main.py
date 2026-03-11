"""Harper agent: MemGPT-style agentic loop with persistent memory and LLM-invokable tools."""
from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

from harper_agent.agent_loop import run_agent_loop_memgpt


def _log_trace(trace_id: str | None, step: str, **kwargs: str) -> None:
    """Structured log for observability (design §22)."""
    if not trace_id:
        return
    parts = [f"trace_id={trace_id}", f"step={step}"] + [f"{k}={v}" for k, v in kwargs.items() if v is not None]
    logger.info("harper_turn %s", " ".join(parts))


def _result(
    narrative: str,
    list_items: list[str] | None = None,
    references: list[dict] | None = None,
    suggested_follow_ups: list[str] | None = None,
) -> dict:
    """Standard agent result dict for API."""
    out = {"narrative": narrative}
    if list_items:
        out["list_items"] = list_items
    if references:
        out["references"] = references
    if suggested_follow_ups:
        out["suggested_follow_ups"] = suggested_follow_ups
    return out


def run_agent_loop(
    session_id: str,
    user_message: str,
    goal: str | None = None,
    tenant_id: str | None = None,
    trace_id: str | None = None,
    stream_callback: Callable[[str, Any], None] | None = None,
) -> dict:
    """MemGPT-style agentic loop: LLM decides when to search recall/archival, edit working context, and respond."""
    _log_trace(trace_id, "session_load", session_id=session_id)
    result = run_agent_loop_memgpt(
        session_id,
        user_message,
        goal=goal,
        tenant_id=tenant_id,
        trace_id=trace_id,
    )
    out = _result(
        result["narrative"],
        references=result.get("references"),
        suggested_follow_ups=result.get("suggested_follow_ups"),
    )
    if stream_callback:
        stream_callback("result", out)
    return out
