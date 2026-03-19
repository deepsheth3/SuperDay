"""MemGPT-style agentic loop: event -> queue manager -> LLM -> function executor -> response."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from harper_agent.agent_prompts import get_system_prompt
from harper_agent.config import get_memory_root
from harper_agent.function_executor import (
    execute_tool,
    parse_llm_output,
    ToolContext,
)
from harper_agent.models import TurnRecord
from harper_agent.queue_manager import (
    DEFAULT_MAX_CONTEXT_TOKENS,
    evict_oldest_messages,
    MEMORY_PRESSURE_MESSAGE,
    should_inject_memory_pressure,
)
from harper_agent.session_manager import (
    append_turn,
    get_session,
    save_session,
    set_session_goal,
)
from harper_agent.transcript_service import persist_exchange_async

logger = logging.getLogger(__name__)

MAX_AGENT_ITERATIONS = 15


def _call_llm(main_context: str, max_output_tokens: int = 1024) -> str | None:
    """Single LLM call with full main context. Returns completion text or None."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        config = types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=max_output_tokens,
        )
        for model in ("gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=main_context,
                    config=config,
                )
                text = getattr(response, "text", None)
                if not text and getattr(response, "candidates", None) and response.candidates:
                    c = response.candidates[0]
                    if getattr(c, "content", None) and getattr(c.content, "parts", None) and c.content.parts:
                        text = getattr(c.content.parts[0], "text", None)
                if text:
                    return text.strip()
            except Exception as e:
                if "429" in str(e).upper() or "RESOURCE_EXHAUSTED" in str(e).upper():
                    continue
                logger.warning("LLM call failed: %s", e)
                return None
    except Exception as e:
        logger.warning("LLM client failed: %s", e)
    return None


def _build_main_context(
    system_prompt: str,
    working_context: str,
    turn_history: list[TurnRecord],
    inject_memory_pressure: bool = False,
) -> str:
    """Build the full prompt string: system + working context + FIFO messages."""
    parts = [system_prompt, "\n\n--- Working context ---\n", working_context or "(none)"]
    parts.append("\n\n--- Recent messages ---\n")
    for t in turn_history:
        role = t.role
        msg = t.message or ""
        parts.append(f"{role}: {msg}\n")
    if inject_memory_pressure:
        parts.append("\n" + MEMORY_PRESSURE_MESSAGE + "\n")
    parts.append("\nRespond (plain text reply to user, or a JSON function call):\n")
    return "".join(parts)


def run_agent_loop_memgpt(
    session_id: str,
    user_message: str,
    *,
    goal: str | None = None,
    tenant_id: str | None = None,
    trace_id: str | None = None,
    request_id: str | None = None,
) -> dict:
    """Run the MemGPT-style agentic loop: append user message, manage queue, call LLM, execute tools, return final response."""
    root = get_memory_root(tenant_id)
    try:
        state = get_session(session_id, tenant_id=tenant_id)
    except Exception:
        from harper_agent.models import SessionState

        state = SessionState(session_id=session_id, tenant_id=tenant_id)
        save_session(session_id, state)

    if tenant_id is not None:
        state.tenant_id = tenant_id
    if goal is not None:
        set_session_goal(state, goal)

    query = (user_message or "").strip()
    if not query:
        from harper_agent import messages as msg
        return {"narrative": msg.MSG_EMPTY_QUERY, "references": None, "suggested_follow_ups": None}

    append_turn(state, "user", query)
    system_prompt = get_system_prompt(max_tokens=DEFAULT_MAX_CONTEXT_TOKENS)

    evict_oldest_messages(state, system_prompt=system_prompt, max_tokens=DEFAULT_MAX_CONTEXT_TOKENS)

    ctx: ToolContext = {
        "session_id": session_id,
        "state": state,
        "tenant_id": tenant_id,
        "root": root,
    }

    narrative: str | None = None
    last_account_id: str | None = None
    last_suggested_follow_ups: list[str] | None = None
    for _ in range(MAX_AGENT_ITERATIONS):
        inject_pressure = should_inject_memory_pressure(state, system_prompt, DEFAULT_MAX_CONTEXT_TOKENS)
        main_context = _build_main_context(
            system_prompt,
            state.working_context or "",
            state.turn_history,
            inject_memory_pressure=inject_pressure,
        )
        completion = _call_llm(main_context)
        if not completion:
            narrative = "I couldn't generate a response. Please try again."
            break

        kind, msg_or_name, args, request_heartbeat = parse_llm_output(completion)

        if kind == "message":
            narrative = msg_or_name or ""
            break

        if kind == "function_call":
            name = (msg_or_name or "").strip()
            if name in ("send_message", "message"):
                narrative = (args or {}).get("message") or (args or {}).get("content") or ""
                raw = (args or {}).get("suggested_follow_ups")
                if isinstance(raw, list):
                    last_suggested_follow_ups = [
                        str(s).strip() for s in raw[:4]
                        if s and str(s).strip()
                    ] or None
                break
            try:
                result = execute_tool(name, args or {}, ctx)
            except ValueError as e:
                result = f"Error: {e}"
            append_turn(state, "assistant", f"[Tool {name}]\n{result}")
            if name in ("archival_storage.get_evidence", "get_evidence", "compose_answer", "compose") and state.recent_account_ids:
                last_account_id = state.recent_account_ids[-1]
            if not request_heartbeat:
                narrative = result
                break
            evict_oldest_messages(state, system_prompt=system_prompt, max_tokens=DEFAULT_MAX_CONTEXT_TOKENS)
            continue

        narrative = completion
        break

    if narrative is None:
        narrative = "I didn't get a clear response. Please try again."

    append_turn(state, "assistant", narrative, resolved_account_id=last_account_id)
    save_session(session_id, state)
    persist_exchange_async(
        session_id,
        query,
        narrative,
        tenant_id=tenant_id,
        request_id=request_id,
        root=root,
    )

    return {
        "narrative": narrative,
        "references": None,
        "suggested_follow_ups": last_suggested_follow_ups,
    }
