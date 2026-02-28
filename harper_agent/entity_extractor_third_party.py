"""Entity extraction via LLM helper agent only. No query-specific regexes."""
from __future__ import annotations

import json
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from harper_agent.models import (
    EntityConstraints,
    EntityFrame,
    EntityHints,
    EntityReference,
    PrimaryEntityType,
    ReferenceType,
    SessionState,
)
# Reference data only: US state name -> 2-letter code (no query logic)
US_STATE_TO_CODE = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "florida": "FL", "georgia": "GA",
    "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV", "new jersey": "NJ",
    "new mexico": "NM", "new york": "NY", "north carolina": "NC", "north dakota": "ND",
    "ohio": "OH", "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI",
    "south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX",
    "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY",     "district of columbia": "DC",
}


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
        focus_line = f"\nCurrent focus in session: type={af.type} id={af.id}. If the user refers to this (e.g. 'that', 'that company', 'from that', 'that one', 'that account', 'them', 'that application'), set anaphora=true and refers_to=\"{af.type}\"."
    prompt = f"""You are an entity extraction helper. Output exactly one JSON object. No markdown, no explanation.

Rules:
- industry: use ONLY one of these exact strings or null: {json.dumps(industries)}
- status: use ONLY one of these exact strings or null: {json.dumps(statuses)}
- state: 2-letter US code (CO, CA, NY, NC, etc.).
- city: lowercase slug (e.g. austin, new_york).
{focus_line}
- For list/filter queries set constraints so the system can find matches: "list all public sector accounts" -> industry: "public_sector"; "accounts awaiting documents" -> status: "awaiting_documents"; "hospitality policy bound" -> industry: "hospitality", status: "policy_bound"; "retail accounts require documents" -> industry: "consumer_goods_retail", status: "awaiting_documents". Use exact keys from the lists above.

Output this JSON only:
{{"primary_entity_type":"account|person|industry|location|unknown","entity_hints":{{"account_name":null|string,"person_name":null|string,"agent_name":null}},"constraints":{{"city":null|string,"state":null|string,"industry":null|string,"status":null|string}},"reference":{{"anaphora":true|false,"refers_to":null|"account"|"person"}}}}

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
        return EntityFrame(
            primary_entity_type=primary,
            entity_hints=EntityHints(
                account_name=hints.get("account_name"),
                person_name=hints.get("person_name"),
                agent_name=hints.get("agent_name"),
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
        )
    except Exception:
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
