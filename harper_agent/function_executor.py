"""MemGPT-style function executor: parse LLM output, dispatch tools, support heartbeat."""
from __future__ import annotations

import json
import re
from typing import Any, TypedDict

from harper_agent.answer_composer import compose_answer
from harper_agent.archival_storage import (
    archival_storage_get_evidence,
    archival_storage_search,
    resolve_account_id,
)
from harper_agent.config import get_memory_root
from harper_agent.evidence_bundler import build_evidence_bundle_from_account_data
from harper_agent.models import SessionState
from harper_agent.session_manager import (
    update_recent_entities,
    working_context_append,
    working_context_get,
    working_context_replace,
)
from harper_agent.transcript_service import recall_storage_search


class ToolContext(TypedDict, total=False):
    session_id: str
    state: SessionState
    tenant_id: str | None
    root: Any  # Path | None


def _parse_function_block(text: str) -> dict[str, Any] | None:
    """Extract JSON function call from LLM output. Looks for ```json ... ``` or last JSON object."""
    text = (text or "").strip()
    # Try ```json ... ``` block first
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        raw = match.group(1).strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    # Try last {...} in the text (function call at end)
    for match in re.finditer(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text):
        pass
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    # Try parsing entire text as JSON (single object)
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and obj.get("function") or obj.get("name"):
            return obj
    except json.JSONDecodeError:
        pass
    return None


def parse_llm_output(
    text: str,
) -> tuple[str, str | None, dict[str, Any] | None, bool]:
    """Parse LLM completion. Returns (kind, message_or_name, args_or_none, request_heartbeat).
    kind is "message" or "function_call". For "message", message_or_name is the reply text. For "function_call", message_or_name is tool name, args_or_none is arguments dict.
    """
    text = (text or "").strip()
    request_heartbeat = False
    # Check for explicit function call block
    obj = _parse_function_block(text)
    if obj and isinstance(obj, dict):
        name = obj.get("function") or obj.get("name") or ""
        args = obj.get("arguments") or obj.get("args") or {}
        if not isinstance(args, dict):
            args = {}
        request_heartbeat = bool(obj.get("request_heartbeat") or obj.get("heartbeat"))
        if name:
            return "function_call", name.strip(), args, request_heartbeat
    # Otherwise full output is the message to user
    return "message", text or None, None, False


def execute_tool(
    name: str,
    arguments: dict[str, Any],
    ctx: ToolContext,
) -> str:
    """Execute one tool and return result string for context. Raises ValueError on unknown tool or invalid args."""
    session_id = ctx.get("session_id") or ""
    state = ctx.get("state")
    tenant_id = ctx.get("tenant_id")
    root = ctx.get("root") or get_memory_root(tenant_id)

    name = (name or "").strip().lower()
    args = arguments or {}

    if name == "recall_storage.search":
        query = args.get("query") or args.get("q") or ""
        page = int(args.get("page") or 1)
        limit = int(args.get("limit") or 10)
        snippets, total = recall_storage_search(
            session_id, query, page=page, limit=limit, tenant_id=tenant_id, root=root
        )
        if not snippets:
            return f"Recall search: no results (total={total})."
        return f"Recall search (total={total}, page={page}):\n" + "\n".join(snippets)

    if name == "archival_storage.search":
        query = args.get("query") or args.get("q") or ""
        page = int(args.get("page") or 1)
        limit = int(args.get("limit") or 10)
        state_f = args.get("state")
        industry = args.get("industry")
        status = args.get("status")
        city = args.get("city")
        account_name = args.get("account_name")
        person_name = args.get("person_name")
        snippets, total = archival_storage_search(
            query=query,
            state=state_f,
            industry=industry,
            status=status,
            city=city,
            account_name=account_name,
            person_name=person_name,
            page=page,
            limit=limit,
            root=root,
        )
        if not snippets:
            return f"Archival search: no results (total={total})."
        return f"Archival search (total={total}, page={page}):\n" + "\n".join(snippets)

    if name == "archival_storage.get_evidence" or name == "get_evidence":
        account_id = (args.get("account_id") or args.get("account") or "").strip()
        scope = (args.get("scope") or "full").strip()
        if not account_id:
            return "Error: get_evidence requires account_id."
        resolved_id = resolve_account_id(account_id, root)
        if resolved_id is None:
            return f"No account found for '{account_id}'."
        if state:
            update_recent_entities(state, account_id=resolved_id)
            working_context_append(state, f"Current account: {resolved_id}")
        lines = archival_storage_get_evidence(resolved_id, scope=scope, root=root)
        if not lines:
            return f"No evidence for account {resolved_id}."
        return "Evidence:\n" + "\n".join(lines)

    if name == "working_context.append":
        text = args.get("text") or args.get("content") or ""
        if not state:
            return "Error: no session state for working_context.append."
        working_context_append(state, text)
        return f"Appended to working context. Current length: {len(state.working_context or '')} chars."

    if name == "working_context.replace":
        old_s = args.get("old") or args.get("old_string") or ""
        new_s = args.get("new") or args.get("new_string") or ""
        if not state:
            return "Error: no session state for working_context.replace."
        working_context_replace(state, old_s, new_s)
        return "Replaced in working context."

    if name == "working_context.get":
        if not state:
            return "Error: no session state."
        content = working_context_get(state)
        return content if content else "(working context empty)"

    if name == "compose_answer" or name == "compose":
        account_id = (args.get("account_id") or args.get("account") or "").strip()
        query = (args.get("query") or args.get("q") or "").strip()
        scope = (args.get("scope") or "full").strip()
        session_goal = (args.get("session_goal") or "").strip() or None
        if not account_id or not query:
            return "Error: compose_answer requires account_id and query."
        resolved_id = resolve_account_id(account_id, root)
        if resolved_id is None:
            return f"No account found for '{account_id}'."
        if state:
            update_recent_entities(state, account_id=resolved_id)
            working_context_append(state, f"Current account: {resolved_id}")
        bundle = build_evidence_bundle_from_account_data(resolved_id, root, scope=scope)
        if not bundle.items:
            return f"No evidence for account {resolved_id}."
        composed = compose_answer(bundle, query, session_goal=session_goal)
        return composed.narrative or "(no narrative)"

    if name == "send_message" or name == "message":
        # Final reply to user: content is in arguments; executor returns it so agent loop can use as response
        return (args.get("message") or args.get("content") or "").strip() or "(empty message)"

    raise ValueError(f"Unknown tool: {name}")


# Tool schemas for system prompt (used by agent loop / prompt builder)
TOOL_SCHEMAS = [
    {
        "name": "recall_storage.search",
        "description": "Search past conversation (recall storage) for this session. Use to find what was said earlier.",
        "arguments": ["query (optional)", "page (default 1)", "limit (default 10)"],
    },
    {
        "name": "archival_storage.search",
        "description": "Search account/business memory (archival storage) by query or filters (state, industry, status, city, account_name, person_name).",
        "arguments": ["query (optional)", "state", "industry", "status", "city", "account_name", "person_name", "page", "limit"],
    },
    {
        "name": "archival_storage.get_evidence",
        "description": "Get full evidence bundle for one account_id. Scope: full, status_only, contact_only, recent_activity, minimal.",
        "arguments": ["account_id", "scope (default full)"],
    },
    {
        "name": "working_context.append",
        "description": "Append a fact or note to your working context (key facts about the user or current task).",
        "arguments": ["text"],
    },
    {
        "name": "working_context.replace",
        "description": "Replace a substring in working context with new text (e.g. update a fact).",
        "arguments": ["old (substring to replace)", "new (replacement)"],
    },
    {
        "name": "working_context.get",
        "description": "Read current working context.",
        "arguments": [],
    },
    {
        "name": "compose_answer",
        "description": "Generate a cited, grounded answer from evidence for one account. Use after get_evidence or when you have an account_id.",
        "arguments": ["account_id", "query", "scope (optional, default full)", "session_goal (optional)"],
    },
    {
        "name": "send_message",
        "description": "Send your final reply to the user. Use when you are done with tool use and want to respond. Include request_heartbeat: false.",
        "arguments": ["message (your reply text)"],
    },
]
