"""Harper agent: extract entities -> navigate indices -> resolve -> evidence -> answer."""
from __future__ import annotations

import re

from harper_agent.answer_composer import compose_answer
from harper_agent.citation_verifier import verify_citations
from harper_agent.config import get_memory_root
from harper_agent.constants import (
    SOURCE_PATH_CALLS,
    SOURCE_PATH_EMAILS,
    SOURCE_PATH_PROFILE,
    SOURCE_PATH_STATUS,
)
from harper_agent.entity_extractor_third_party import extract_entities, resolve_disambiguation_reply
from harper_agent.evidence_bundler import build_evidence_bundle_from_account_data
from harper_agent.index_navigator import navigate
from harper_agent.models import (
    EvidenceBundle,
    EntityFrame,
    EntityHints,
    PendingDisambiguation,
    PrimaryEntityType,
)
from harper_agent.proactive_suggestions import suggest_follow_ups
from harper_agent.resolver import resolve
from harper_agent.session_manager import (
    append_turn,
    get_session,
    save_session,
    set_active_focus,
    set_last_intent_constraints,
    set_session_goal,
    update_recent_entities,
)
from harper_agent.intent_handlers import (
    handle_compare_accounts,
    handle_summarize_activity,
    handle_suggest_next_action,
)
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
    if SOURCE_PATH_PROFILE in path:
        return SOURCE_PATH_PROFILE
    if SOURCE_PATH_STATUS in path:
        return SOURCE_PATH_STATUS
    if SOURCE_PATH_EMAILS in path and sid:
        return f"emails/{sid}"
    if SOURCE_PATH_CALLS in path and sid:
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


def _intent_from_frame(frame: EntityFrame) -> str:
    """Derive last_intent for session from entity frame. Prefer frame.intent when set by extractor."""
    if getattr(frame, "intent", None) and frame.intent != "unknown":
        return frame.intent
    if frame.reference.anaphora:
        return "follow_up"
    if frame.entity_hints.account_name or frame.entity_hints.person_name:
        return "status_query"
    c = frame.constraints
    if any(getattr(c, k) for k in ("city", "state", "industry", "status") if getattr(c, k)):
        return "list_accounts"
    return frame.primary_entity_type.value if frame.primary_entity_type else "unknown"


def _constraints_from_frame(frame: EntityFrame) -> dict[str, str]:
    """Extract non-null constraints as plain dict for session."""
    c = frame.constraints
    out = {}
    for k in ("city", "state", "industry", "status"):
        v = getattr(c, k, None)
        if v:
            out[k] = str(v)
    return out


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


def run_agent_loop(session_id: str, user_message: str, goal: str | None = None) -> dict:
    root = get_memory_root()
    state = get_session(session_id)
    if goal is not None:
        set_session_goal(state, goal)
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
            answer = compose_answer(bundle, orig_query, state.session_goal)
            if not verify_citations(answer, bundle):
                answer.narrative += " (Citations could not be fully verified.)"
            suggested = suggest_follow_ups(bundle, chosen_id, root, state.session_goal)
            append_turn(state, "user", query)
            append_turn(state, "assistant", answer.narrative, resolved_account_id=chosen_id, references=_build_references(bundle, answer.narrative))
            update_recent_entities(state, account_id=chosen_id)
            set_active_focus(state, "account", chosen_id, 1.0)
            save_session(session_id, state)
            return _result(answer.narrative, references=_build_references(bundle, answer.narrative), suggested_follow_ups=suggested if suggested else None)
        # Can't interpret as a choice; clear and fall through to normal flow
        state.pending_disambiguation = None

    frame = extract_entities(query, state, root)
    set_last_intent_constraints(state, _intent_from_frame(frame), _constraints_from_frame(frame))
    if goal is None and getattr(frame, "session_goal_hint", None):
        set_session_goal(state, frame.session_goal_hint)

    # Session-aware: use last focused account only when helper sets anaphora (no query-specific rules)
    if frame.reference.anaphora and state.active_focus and state.active_focus.type == "account":
        resolved_ids, disambig, n_candidates = [state.active_focus.id], None, 1
    else:
        candidate_ids, nav_error = navigate(frame, root)
        if nav_error:
            return _result(f"I had trouble searching the index: {nav_error}.")
        resolved_ids, disambig, n_candidates = resolve(frame, candidate_ids, root)
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

    # Compare two accounts: resolve each name from compare_account_names
    compare_names = getattr(frame.entity_hints, "compare_account_names", None) or []
    if getattr(frame, "intent", None) == "compare_accounts" and len(compare_names) >= 2:
        cand_ids, nav_err = navigate(frame, root)
        if nav_err:
            return _result(f"I had trouble searching the index: {nav_err}.")
        ids_for_compare = []
        for name in compare_names[:2]:
            f = EntityFrame(
                primary_entity_type=PrimaryEntityType.ACCOUNT,
                entity_hints=EntityHints(account_name=name),
                constraints=frame.constraints,
                reference=frame.reference,
            )
            matched, _, _ = resolve(f, cand_ids, root)
            if matched:
                ids_for_compare.append(matched[0])
        if len(ids_for_compare) == 2:
            narrative = handle_compare_accounts(ids_for_compare[0], ids_for_compare[1], query, root)
            append_turn(state, "user", query)
            append_turn(state, "assistant", narrative)
            update_recent_entities(state, account_id=ids_for_compare[0])
            update_recent_entities(state, account_id=ids_for_compare[1])
            set_active_focus(state, "account", ids_for_compare[0], 1.0)
            save_session(session_id, state)
            return _result(narrative)
        return _result("I couldn't identify both accounts to compare. Please name the two accounts.")

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

    # Intent-specific handlers (summarize_activity, suggest_next_action)
    if getattr(frame, "intent", None) == "summarize_activity":
        narrative = handle_summarize_activity(account_id, query, root)
        suggested = suggest_follow_ups(bundle, account_id, root, state.session_goal)
        append_turn(state, "user", query)
        append_turn(state, "assistant", narrative, resolved_account_id=account_id)
        update_recent_entities(state, account_id=account_id)
        set_active_focus(state, "account", account_id, 1.0)
        save_session(session_id, state)
        return _result(narrative, suggested_follow_ups=suggested if suggested else None)
    if getattr(frame, "intent", None) == "suggest_next_action":
        narrative = handle_suggest_next_action(account_id, query, root)
        suggested = suggest_follow_ups(bundle, account_id, root, state.session_goal)
        append_turn(state, "user", query)
        append_turn(state, "assistant", narrative, resolved_account_id=account_id)
        update_recent_entities(state, account_id=account_id)
        set_active_focus(state, "account", account_id, 1.0)
        save_session(session_id, state)
        return _result(narrative, suggested_follow_ups=suggested if suggested else None)

    answer = compose_answer(bundle, query, state.session_goal)
    if not verify_citations(answer, bundle):
        answer.narrative += " (Citations could not be fully verified.)"
    confidence_prefix = ""
    if n_candidates > 1:
        confidence_prefix = "I narrowed it down to one match from several. "
    narrative = confidence_prefix + answer.narrative

    suggested = suggest_follow_ups(bundle, account_id, root, state.session_goal)

    append_turn(state, "user", query)
    append_turn(state, "assistant", narrative, resolved_account_id=account_id, references=_build_references(bundle, answer.narrative))
    update_recent_entities(state, account_id=account_id)
    set_active_focus(state, "account", account_id, 1.0)
    save_session(session_id, state)

    return _result(narrative, references=_build_references(bundle, answer.narrative), suggested_follow_ups=suggested if suggested else None)
