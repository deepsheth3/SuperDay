"""Harper agent: extract entities -> navigate indices -> resolve -> evidence -> answer."""
from __future__ import annotations

import re

from harper_agent.answer_composer import compose_answer
from harper_agent.citation_verifier import verify_citations
from harper_agent.config import get_memory_root
from harper_agent.entity_extractor_third_party import extract_entities, resolve_disambiguation_reply
from harper_agent.evidence_bundler import build_evidence_bundle_from_account_data
from harper_agent.index_navigator import navigate
from harper_agent.models import EvidenceBundle, PendingDisambiguation
from harper_agent.resolver import resolve
from harper_agent.session_manager import append_turn, get_session, save_session, set_active_focus
from harper_agent.tools import object_get_account


def _cited_indices(narrative: str) -> set[int]:
    """Parse [1], [2], [1, 2], [3-9] from narrative and return set of cited 1-based indices."""
    cited = set()
    for m in re.finditer(r"\[([^\]]+)\]", narrative or ""):
        ref = m.group(1).strip().replace(" ", "")
        if ref.isdigit():
            cited.add(int(ref))
            continue
        if "," in ref and all(p.isdigit() for p in ref.split(",")):
            cited.update(int(p) for p in ref.split(","))
            continue
        if "-" in ref:
            parts = ref.split("-", 1)
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                cited.update(range(int(parts[0]), int(parts[1]) + 1))
    return cited


def _short_ref_label(item) -> str:
    """Short folder-style label for a reference (e.g. account/profile, emails/email_001)."""
    path = (item.source_path or "").strip()
    sid = (item.source_id or "").strip()
    if "account/profile" in path:
        return "account/profile"
    if "account/status" in path:
        return "account/status"
    if "account/emails" in path and sid:
        return f"emails/{sid}"
    if "account/calls" in path and sid:
        return f"calls/{sid}"
    return path or sid or "source"


def _build_references(bundle: EvidenceBundle, narrative: str | None = None) -> list[dict]:
    """Build references: short folder-style labels; only cited indices if narrative given."""
    cited = _cited_indices(narrative or "") if narrative else None
    use_only_cited = cited is not None and len(cited) > 0
    refs = []
    for i, item in enumerate(bundle.items, 1):
        if use_only_cited and i not in cited:
            continue
        label = _short_ref_label(item)
        refs.append({"num": i, "source_id": item.source_id or "", "label": label})
    return refs


def _result(narrative: str, list_items: list[str] | None = None, references: list[dict] | None = None) -> dict:
    """Standard agent result dict for API."""
    out = {"narrative": narrative}
    if list_items:
        out["list_items"] = list_items
    if references:
        out["references"] = references
    return out


def run_agent_loop(session_id: str, user_message: str) -> dict:
    root = get_memory_root()
    state = get_session(session_id)
    query = (user_message or "").strip()
    if not query:
        return _result("Please ask a question about an account, contact, or status.")

    # Disambiguation: let LLM interpret user's reply (no regex or query rules)
    pending = state.pending_disambiguation
    if pending and pending.candidates:
        chosen_id = resolve_disambiguation_reply(query, pending.candidates)
        if chosen_id:
            state.pending_disambiguation = None
            orig_query = (pending.original_query or query).strip() or query
            bundle = build_evidence_bundle_from_account_data(chosen_id, root)
            answer = compose_answer(bundle, orig_query)
            if not verify_citations(answer, bundle):
                answer.narrative += " (Citations could not be fully verified.)"
            append_turn(state, "user", query)
            append_turn(state, "assistant", answer.narrative, resolved_account_id=chosen_id, references=_build_references(bundle, answer.narrative))
            set_active_focus(state, "account", chosen_id, 1.0)
            save_session(session_id, state)
            return _result(answer.narrative, references=_build_references(bundle, answer.narrative))
        # Can't interpret as a choice; clear and fall through to normal flow
        state.pending_disambiguation = None

    frame = extract_entities(query, state, root)

    # Session-aware: use last focused account only when helper sets anaphora (no query-specific rules)
    if frame.reference.anaphora and state.active_focus and state.active_focus.type == "account":
        resolved_ids, disambig = [state.active_focus.id], None
    else:
        candidate_ids, nav_error = navigate(frame, root)
        if nav_error:
            return _result(f"I had trouble searching the index: {nav_error}.")
        resolved_ids, disambig = resolve(frame, candidate_ids, root)
    if disambig == "disambiguation" and len(resolved_ids) > 1:
        names = []
        candidates = []
        for aid in resolved_ids[:5]:
            data = object_get_account(aid, root)
            if data:
                p = (data.get("profile") or data.get("full") or {})
                name = p.get("company_name") or p.get("dba_name") or p.get("structured_data", {}).get("company_name") or aid
                names.append(name)
                candidates.append({"account_id": aid, "name": name})
        state.pending_disambiguation = PendingDisambiguation(
            candidates=candidates,
            original_query=query,
        )
        list_items = [f"{i + 1}. {n}" for i, n in enumerate(names)]
        msg = "Multiple accounts match. Which one do you mean? (Reply with the number or the full name.)"
        append_turn(state, "user", query)
        append_turn(state, "assistant", msg, list_items=list_items)
        save_session(session_id, state)
        return _result(msg, list_items=list_items)

    if not resolved_ids:
        return _result("I couldn't find any accounts matching that.")

    # Location/industry-only (no specific account): return list of matching account names
    if len(resolved_ids) > 1 and not (frame.entity_hints.account_name or frame.reference.anaphora):
        names = []
        for aid in resolved_ids[:20]:
            data = object_get_account(aid, root)
            if data:
                p = data.get("profile") or data.get("full") or {}
                name = p.get("company_name") or p.get("dba_name") or (p.get("structured_data") or {}).get("company_name") or aid
                names.append(name)
        intro = "Accounts matching:" if len(resolved_ids) <= 20 else f"Accounts matching (first 20 of {len(resolved_ids)}):"
        return _result(intro, list_items=names)

    account_id = resolved_ids[0]
    bundle = build_evidence_bundle_from_account_data(account_id, root)
    answer = compose_answer(bundle, query)
    if not verify_citations(answer, bundle):
        answer.narrative += " (Citations could not be fully verified.)"

    append_turn(state, "user", query)
    append_turn(state, "assistant", answer.narrative, resolved_account_id=account_id, references=_build_references(bundle, answer.narrative))
    set_active_focus(state, "account", account_id, 1.0)
    save_session(session_id, state)

    return _result(answer.narrative, references=_build_references(bundle, answer.narrative))
