"""Intent-specific handlers: compare accounts, summarize activity, suggest next action."""
from __future__ import annotations

import os
from pathlib import Path

from harper_agent.config import get_memory_root
from harper_agent.constants import (
    get_confirm_binding_statuses,
    get_confirm_next_steps_statuses,
    get_waiting_on_client_statuses,
    normalize_status_key,
)
from harper_agent.evidence_bundler import build_evidence_bundle_from_account_data
from harper_agent.models import EvidenceBundle
from harper_agent.tools import object_get_account


def _evidence_to_lines(bundle: EvidenceBundle, prefix: str = "") -> str:
    """Compact text for LLM from evidence items."""
    lines = []
    for i, item in enumerate(bundle.items, 1):
        c = item.content
        if not isinstance(c, dict):
            lines.append(f"{prefix}[{i}] {str(c)[:150]}")
            continue
        if "company_name" in c:
            name = c.get("company_name", "")
            addr = c.get("address") or (c.get("structured_data") or {})
            city = addr.get("city") or (c.get("structured_data") or {}).get("city", "")
            state = addr.get("state") or (c.get("structured_data") or {}).get("state", "")
            lines.append(f"{prefix}[{i}] Account: {name} — {city}, {state}.")
        elif "current_status" in c or "status" in c:
            lines.append(f"{prefix}[{i}] Status: {c.get('current_status') or c.get('status', 'N/A')}.")
        elif "subject" in c:
            lines.append(f"{prefix}[{i}] Email: {c.get('subject', '')} ({c.get('sent_at', '')}).")
        elif "call_summary" in c:
            lines.append(f"{prefix}[{i}] Call: {c.get('call_summary', '')} ({c.get('started_at', '')}).")
        else:
            lines.append(f"{prefix}[{i}] {str(c)[:120]}.")
    return "\n".join(lines) if lines else "No evidence."


def _call_llm(prompt: str, max_tokens: int = 400) -> str | None:
    """Single LLM call; returns None on failure."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from google import genai
        from google.genai import types
        from google.genai import errors as genai_errors

        client = genai.Client(api_key=api_key)
        config = types.GenerateContentConfig(temperature=0.2, max_output_tokens=max_tokens)
        for model in ("gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"):
            try:
                response = client.models.generate_content(model=model, contents=prompt, config=config)
                text = getattr(response, "text", None)
                if not text and getattr(response, "candidates", None) and response.candidates:
                    c = response.candidates[0]
                    if getattr(c, "content", None) and getattr(c.content, "parts", None) and c.content.parts:
                        text = getattr(c.content.parts[0], "text", None)
                if text:
                    return text.strip()
            except genai_errors.ClientError as e:
                if "429" not in str(e).upper() and "RESOURCE_EXHAUSTED" not in str(e).upper():
                    return None
                continue
    except Exception:
        pass
    return None


def handle_compare_accounts(
    account_id_a: str,
    account_id_b: str,
    query: str,
    root: Path | None = None,
) -> str:
    """Load two evidence bundles, compare via LLM; return 2–4 sentence narrative."""
    root = root or get_memory_root()
    bundle_a = build_evidence_bundle_from_account_data(account_id_a, root)
    bundle_b = build_evidence_bundle_from_account_data(account_id_b, root)
    text_a = _evidence_to_lines(bundle_a, "A: ")
    text_b = _evidence_to_lines(bundle_b, "B: ")
    prompt = f"""You are comparing two insurance accounts for a user. Write a short comparison (2–4 sentences) covering status, location, contacts, and recent activity. Be concise.

Account A evidence:
{text_a}

Account B evidence:
{text_b}

User question: {query or 'Compare these two accounts.'}

Reply with only the comparison. No preamble."""

    out = _call_llm(prompt)
    if out:
        return out
    # Fallback: minimal comparison from profile/status
    data_a = object_get_account(account_id_a, root)
    data_b = object_get_account(account_id_b, root)
    name_a = (data_a or {}).get("profile") or (data_a or {}).get("full", {})
    name_b = (data_b or {}).get("profile") or (data_b or {}).get("full", {})
    name_a = name_a.get("company_name", name_a.get("dba_name", account_id_a)) if isinstance(name_a, dict) else account_id_a
    name_b = name_b.get("company_name", name_b.get("dba_name", account_id_b)) if isinstance(name_b, dict) else account_id_b
    status_a = (data_a or {}).get("status") or {}
    status_b = (data_b or {}).get("status") or {}
    s_a = status_a.get("current_status", status_a.get("status", "N/A")) if isinstance(status_a, dict) else "N/A"
    s_b = status_b.get("current_status", status_b.get("status", "N/A")) if isinstance(status_b, dict) else "N/A"
    return f"{name_a} is in {s_a} status. {name_b} is in {s_b} status."


def handle_summarize_activity(account_id: str, query: str, root: Path | None = None) -> str:
    """Summarize recent communications (emails/calls) for the account. Reuses composer or dedicated prompt."""
    root = root or get_memory_root()
    bundle = build_evidence_bundle_from_account_data(account_id, root)
    # Emphasize emails and calls
    comm_items = [i for i in bundle.items if "emails" in (i.source_path or "") or "calls" in (i.source_path or "")]
    has_comm = bool(comm_items)
    if has_comm:
        comm_bundle = EvidenceBundle(items=comm_items)
        evidence_text = _evidence_to_lines(comm_bundle)
    else:
        evidence_text = _evidence_to_lines(bundle)

    prompt = f"""Summarize only recent emails and calls (communications) for this account. Be brief (2–4 sentences). Use citation numbers [1], [2] when referring to specific items.

Evidence:
{evidence_text}

User question: {query or 'Summarize recent activity.'}

Write only the summary with inline citations. No preamble."""

    out = _call_llm(prompt, max_tokens=350)
    if out:
        return out
    if has_comm:
        return "Recent emails and calls are on record; details are in the evidence above."
    return "No recent communications found for this account."


def handle_suggest_next_action(account_id: str, query: str, root: Path | None = None) -> str:
    """Rule-based or short LLM: suggest next step from status and follow-up state. Uses status set membership only."""
    root = root or get_memory_root()
    data = object_get_account(account_id, root)
    if not data:
        return "I couldn't load this account; no suggestion."
    status_obj = data.get("status")
    raw_status = ""
    if isinstance(status_obj, dict):
        raw_status = status_obj.get("current_status") or status_obj.get("status") or status_obj.get("status_key") or ""
    status_key = normalize_status_key(raw_status)

    try:
        from followup_agent.state import get_followup_state
        followup = get_followup_state(account_id, root) or {}
    except ImportError:
        followup = {}
    followup_count = followup.get("followup_count", 0)

    waiting = get_waiting_on_client_statuses(root)
    if status_key in waiting:
        if followup_count < 2:
            return "Send a follow-up reminder to the client."
        return "You've already sent the maximum follow-ups; consider a different channel or waiting for client response."
    if status_key in get_confirm_next_steps_statuses(root):
        return "Reach out to the client to confirm next steps."
    if status_key in get_confirm_binding_statuses(root):
        return "Confirm binding and any final documentation with the client."
    if status_key:
        return "Review the current status and consider reaching out to the client or underwriter as needed."
    return "Check the account status to decide the next step."
