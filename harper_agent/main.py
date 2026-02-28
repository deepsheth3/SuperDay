"""Harper agent: extract entities -> navigate indices -> resolve -> evidence -> answer."""
from __future__ import annotations

from harper_agent.answer_composer import compose_answer
from harper_agent.citation_verifier import verify_citations
from harper_agent.config import get_memory_root
from harper_agent.entity_extractor_third_party import extract_entities
from harper_agent.evidence_bundler import build_evidence_bundle_from_account_data
from harper_agent.index_navigator import navigate
from harper_agent.resolver import resolve
from harper_agent.session_manager import append_turn, get_session, save_session, set_active_focus
from harper_agent.tools import object_get_account


def run_agent_loop(session_id: str, user_message: str) -> str:
    root = get_memory_root()
    state = get_session(session_id)
    query = (user_message or "").strip()
    if not query:
        return "Please ask a question about an account, contact, or status."

    frame = extract_entities(query, state, root)

    # Session-aware: use last focused account only when helper sets anaphora (no query-specific rules)
    if frame.reference.anaphora and state.active_focus and state.active_focus.type == "account":
        resolved_ids, disambig = [state.active_focus.id], None
    else:
        candidate_ids, nav_error = navigate(frame, root)
        if nav_error:
            return f"I had trouble searching the index: {nav_error}."
        resolved_ids, disambig = resolve(frame, candidate_ids, root)
    if disambig == "disambiguation" and len(resolved_ids) > 1:
        names = []
        for aid in resolved_ids[:5]:
            data = object_get_account(aid, root)
            if data:
                p = (data.get("profile") or data.get("full") or {})
                name = p.get("company_name") or p.get("dba_name") or p.get("structured_data", {}).get("company_name") or aid
                names.append(name)
        return "Multiple accounts match. Which one do you mean? " + ", ".join(names)

    if not resolved_ids:
        return "I couldn't find any accounts matching that."

    # Location/industry-only (no specific account): return list of matching account names
    if len(resolved_ids) > 1 and not (frame.entity_hints.account_name or frame.reference.anaphora):
        names = []
        for aid in resolved_ids[:20]:
            data = object_get_account(aid, root)
            if data:
                p = data.get("profile") or data.get("full") or {}
                name = p.get("company_name") or p.get("dba_name") or (p.get("structured_data") or {}).get("company_name") or aid
                names.append(name)
        return "Accounts matching: " + ", ".join(names) + ("." if len(resolved_ids) <= 20 else f" … and {len(resolved_ids) - 20} more.")

    account_id = resolved_ids[0]
    bundle = build_evidence_bundle_from_account_data(account_id, root)
    answer = compose_answer(bundle, query)
    if not verify_citations(answer, bundle):
        answer.narrative += " (Citations could not be fully verified.)"

    append_turn(state, "user", query)
    append_turn(state, "assistant", answer.narrative, resolved_account_id=account_id)
    set_active_focus(state, "account", account_id, 1.0)
    save_session(session_id, state)

    return answer.narrative
