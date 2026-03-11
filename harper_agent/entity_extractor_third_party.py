"""Entity extraction via LLM helper agent only. No query-specific regexes."""
from __future__ import annotations

import json
import os

try:
    from dotenv import load_dotenv
    from pathlib import Path
    # Project root = parent of harper_agent package
    _root = Path(__file__).resolve().parent.parent
    load_dotenv(_root / ".env")
except ImportError:
    pass

from harper_agent.constants import ALLOWED_SESSION_GOALS, INTENT_VALUES
from harper_agent.models import (
    EntityConstraints,
    EntityFrame,
    EntityHints,
    EntityReference,
    PrimaryEntityType,
    ReferenceType,
    SessionState,
)


def _get_index_keys(root) -> tuple[list[str], list[str]]:
    """Read allowed industry and status keys from the index dir. No hardcoded query logic."""
    from pathlib import Path
    from harper_agent.config import get_memory_root
    root = root or get_memory_root()
    indices = root / "indices"
    industries = []
    statuses = []
    if (indices / "industry").is_dir():
        industries = [d.name for d in (indices / "industry").iterdir() if d.is_dir()]
    if (indices / "status").is_dir():
        statuses = [d.name for d in (indices / "status").iterdir() if d.is_dir()]
    return industries, statuses


def _call_helper_agent(
    query: str,
    session_state: SessionState | None,
    root=None,
) -> EntityFrame | None:
    """Helper agent: LLM extracts entities into EntityFrame. No regexes or query-specific rules.
    On 429 tries alternate models. Requires GEMINI_API_KEY (paid key recommended).
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    industries, statuses = _get_index_keys(root)
    focus_line = ""
    if session_state and session_state.active_focus:
        af = session_state.active_focus
        focus_line = (
            f"\nCurrent focus in session: type={af.type} id={af.id}. "
            "Use anaphora=true ONLY when the user clearly refers to this same focus without naming a different type (e.g. 'that', 'that company', 'from that', 'that one', 'that account', 'them', 'that application'). "
            "If the user names a different kind of account (e.g. 'that public sector account', 'that childcare center in California', 'the hotel in Austin'), set anaphora=false and set constraints (industry, state, city) so we search for the account that matches that description."
        )
    session_ctx = ""
    if session_state:
        parts = []
        if getattr(session_state, "rolling_summary", None) and session_state.rolling_summary:
            parts.append(f"Conversation summary (older turns): {session_state.rolling_summary}")
        if getattr(session_state, "recent_account_ids", None) and session_state.recent_account_ids:
            parts.append(f"Recent accounts in this session (most recent last): {session_state.recent_account_ids}")
        if getattr(session_state, "recent_person_ids", None) and session_state.recent_person_ids:
            parts.append(f"Recent persons in this session: {session_state.recent_person_ids}")
        if getattr(session_state, "last_intent", None) or getattr(session_state, "last_constraints", None):
            intent = getattr(session_state, "last_intent", None) or "none"
            constraints = getattr(session_state, "last_constraints", None) or {}
            parts.append(f"Last query intent: {intent}. Last constraints: {constraints}.")
        if getattr(session_state, "session_goal", None):
            parts.append(f"Current session goal: {session_state.session_goal}. When the query is ambiguous, prefer constraints that match this goal (e.g. checking_follow_ups -> status awaiting_documents or contacted_by_harper; triaging_pipeline -> status filters).")
        if parts:
            session_ctx = "\n" + " ".join(parts)
    intent_values = "|".join(sorted(INTENT_VALUES))
    goal_values = "|".join(sorted(ALLOWED_SESSION_GOALS))
    prompt = f"""You are an entity extraction helper. Output exactly one JSON object. No markdown, no explanation.

Rules:
- industry: use ONLY one of these exact strings or null: {json.dumps(industries)}
- status: use ONLY one of these exact strings or null: {json.dumps(statuses)}
- state: 2-letter US code (CO, CA, NY, NC, etc.).
- city: lowercase slug (e.g. austin, new_york).
{focus_line}{session_ctx}
- For list/filter queries set constraints so the system can find matches: "list all public sector accounts" -> industry: "public_sector"; "accounts awaiting documents" -> status: "awaiting_documents"; "hospitality policy bound" -> industry: "hospitality", status: "policy_bound"; "retail accounts require documents" -> industry: "consumer_goods_retail", status: "awaiting_documents". Use exact keys from the lists above.
- intent: use exactly one of: {", ".join(sorted(INTENT_VALUES))}. Use compare_accounts when the user asks to compare two accounts (e.g. "compare X and Y"). Use summarize_activity when they ask for recent activity/communications. Use suggest_next_action when they ask what to do next or for a recommendation. Otherwise use status_query, list_accounts, follow_up, or unknown.
- When intent is compare_accounts, set entity_hints.compare_account_names to a list of exactly two company/account names (e.g. ["Evergreen Public Services", "Harborline Hotel Group"]). Otherwise set compare_account_names to [].
- session_goal_hint: If the user clearly states what they are trying to do in this session (e.g. "I'm triaging pipeline today", "help me check follow-ups", "preparing outreach", "just reviewing this account"), set session_goal_hint to exactly one of: {", ".join(sorted(ALLOWED_SESSION_GOALS))}. Otherwise null.

Output this JSON only:
{{"primary_entity_type":"account|person|industry|location|unknown","entity_hints":{{"account_name":null|string,"person_name":null|string,"agent_name":null,"compare_account_names":[]|["name1","name2"]}},"constraints":{{"city":null|string,"state":null|string,"industry":null|string,"status":null|string}},"reference":{{"anaphora":true|false,"refers_to":null|"account"|"person"}},"intent":"{intent_values}","session_goal_hint":null|"{goal_values}"}}


User query: {query}"""

    try:
        from google import genai
        from google.genai import types
        from google.genai import errors as genai_errors

        client = genai.Client(api_key=api_key)
        config = types.GenerateContentConfig(temperature=0.1, max_output_tokens=400)
        text = None
        for model in ("gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=config,
                )
                text = getattr(response, "text", None)
                if not text and getattr(response, "candidates", None) and response.candidates:
                    c = response.candidates[0]
                    if getattr(c, "content", None) and getattr(c.content, "parts", None) and c.content.parts:
                        text = getattr(c.content.parts[0], "text", None)
                if text:
                    break
            except genai_errors.ClientError as e:
                err_str = str(e).upper()
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "QUOTA" in err_str:
                    continue
                return None
        if not text:
            return None
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
        data = json.loads(text)
        primary = PrimaryEntityType(data.get("primary_entity_type", "unknown"))
        hints = data.get("entity_hints") or {}
        constraints = data.get("constraints") or {}
        ref = data.get("reference") or {}
        anaphora = ref.get("anaphora", False)
        ref_type = ref.get("refers_to")
        if ref_type and ref_type not in ("account", "person"):
            ref_type = None
        intent_raw = data.get("intent") or "unknown"
        if intent_raw not in INTENT_VALUES:
            intent_raw = "unknown"
        compare_names = hints.get("compare_account_names")
        if not isinstance(compare_names, list):
            compare_names = []
        compare_names = [str(n).strip() for n in compare_names if n][:2]
        goal_hint = data.get("session_goal_hint")
        if goal_hint not in ALLOWED_SESSION_GOALS:
            goal_hint = None
        return EntityFrame(
            primary_entity_type=primary,
            entity_hints=EntityHints(
                account_name=hints.get("account_name"),
                person_name=hints.get("person_name"),
                agent_name=hints.get("agent_name"),
                compare_account_names=compare_names,
            ),
            constraints=EntityConstraints(
                city=constraints.get("city"),
                state=constraints.get("state"),
                industry=constraints.get("industry"),
                status=constraints.get("status"),
            ),
            reference=EntityReference(
                anaphora=anaphora,
                refers_to=ReferenceType(ref_type) if ref_type else None,
            ),
            intent=intent_raw,
            session_goal_hint=goal_hint,
        )
    except Exception:
        return None


def resolve_disambiguation_reply(user_reply: str, candidates: list[dict]) -> str | None:
    """Ask LLM which account the user chose. No regex or query rules; returns account_id or None."""
    if not user_reply or not candidates:
        return None
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    options = "\n".join(f"{i+1}. {c.get('name', '')} (id: {c.get('account_id', '')})" for i, c in enumerate(candidates))
    prompt = f"""We asked the user which account they meant. They replied: "{user_reply}"

Options:
{options}

Output ONLY the account_id they chose (e.g. acct_1eaf057f87), or the single word: none"""
    try:
        from google import genai
        from google.genai import types
        from google.genai import errors as genai_errors
        client = genai.Client(api_key=api_key)
        config = types.GenerateContentConfig(temperature=0, max_output_tokens=64)
        for model in ("gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"):
            try:
                response = client.models.generate_content(model=model, contents=prompt, config=config)
                text = getattr(response, "text", None)
                if not text and getattr(response, "candidates", None) and response.candidates:
                    c = response.candidates[0]
                    if getattr(c, "content", None) and getattr(c.content, "parts", None) and c.content.parts:
                        text = getattr(c.content.parts[0], "text", None)
                if not text:
                    continue
                text = text.strip().lower()
                if text == "none":
                    return None
                account_ids = {c.get("account_id") for c in candidates if c.get("account_id")}
                if text in account_ids:
                    return text
                for aid in account_ids:
                    if aid and aid in text:
                        return aid
                return None
            except genai_errors.ClientError as e:
                if "429" in str(e).upper() or "RESOURCE_EXHAUSTED" in str(e).upper():
                    continue
                return None
    except Exception:
        pass
    return None


def extract_entities(
    query: str,
    session_state: SessionState | None = None,
    root=None,
) -> EntityFrame:
    """Extract entities via LLM helper agent only. Requires GEMINI_API_KEY."""
    frame = _call_helper_agent(query, session_state, root)
    if frame is not None:
        return frame
    raise RuntimeError(
        "Entity extraction failed. Set GEMINI_API_KEY in .env and ensure the API is available."
    )
