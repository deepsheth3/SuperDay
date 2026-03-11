"""Compose a human-friendly summarized answer from evidence, with citations."""
from __future__ import annotations

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from harper_agent.models import ComposedAnswer, EvidenceBundle


def _contact_names_from_bundle(bundle: EvidenceBundle) -> list[str]:
    names = []
    for item in bundle.items:
        c = item.content
        if not isinstance(c, dict):
            continue
        if "contact_name" in c and c.get("contact_name"):
            names.append(c["contact_name"].strip())
        if "from_address" in c and c.get("from_address"):
            addr = c["from_address"]
            if "@" in addr:
                local = addr.split("@")[0]
                name = local.replace(".", " ").replace("_", " ").title()
                if name and name not in names:
                    names.append(name)
    return list(dict.fromkeys(names))


def _evidence_to_prompt_text(bundle: EvidenceBundle) -> str:
    """Turn evidence items into a compact numbered list for the LLM."""
    lines = []
    for i, item in enumerate(bundle.items, 1):
        c = item.content
        if not isinstance(c, dict):
            lines.append(f"[{i}] {str(c)[:200]}")
            continue
        addr = c.get("address") or {}
        if not addr and "structured_data" in c:
            sd = c.get("structured_data") or {}
            addr = {"city": sd.get("city"), "state": sd.get("state")}
        if "company_name" in c:
            name = c.get("company_name", "")
            ind = c.get("industry_primary") or (c.get("structured_data") or {}).get("industry_primary", "")
            city = addr.get("city") or (c.get("structured_data") or {}).get("city", "")
            state = addr.get("state") or (c.get("structured_data") or {}).get("state", "")
            lines.append(f"[{i}] Account: {name} — {ind}; {city}, {state}.")
        elif "current_status" in c or "status" in c:
            lines.append(f"[{i}] Status: {c.get('current_status') or c.get('status', 'N/A')}.")
        elif "subject" in c:
            lines.append(f"[{i}] Email: {c.get('subject', '')} ({c.get('sent_at', '')}).")
        elif "call_summary" in c:
            lines.append(f"[{i}] Call: {c.get('call_summary', '')} — {c.get('contact_name', '')} ({c.get('started_at', '')}).")
        else:
            lines.append(f"[{i}] {str(c)[:150]}.")
    return "\n".join(lines) if lines else "No evidence."


def _summarize_with_llm(
    bundle: EvidenceBundle,
    query: str,
    evidence_text: str,
    session_goal: str | None = None,
) -> str | None:
    """Use Gemini to produce a short, human-friendly summary with citations. Returns None on failure."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        contacts = _contact_names_from_bundle(bundle)
        contact_line = f" Key contacts from the evidence: {', '.join(contacts)}." if contacts else ""
        goal_line = ""
        if session_goal:
            goal_line = f"\nThe user is currently focused on: {session_goal}. Emphasize information that helps with that (e.g. triaging_pipeline -> status and next actions; checking_follow_ups -> last contact and follow-up state; preparing_outreach -> contacts and last touch).\n"

        prompt = f"""You are a helpful assistant summarizing insurance account information. Given the evidence below, write a brief, human-friendly summary (2–4 sentences) that answers the user's question. Use the citation numbers [1], [2], etc. when referring to specific facts. Be concise and easy to read. Do not list raw data; summarize in plain language.
{contact_line}{goal_line}

Evidence:
{evidence_text}

User question: {query or 'Summarize this account.'}

Write only the summary with inline citations (e.g. "The account is in application_submitted status [2]."). No preamble."""

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=500,
            ),
        )
        if response:
            text = getattr(response, "text", None)
            if not text and getattr(response, "candidates", None):
                c = response.candidates[0]
                if getattr(c, "content", None) and c.content.parts:
                    text = c.content.parts[0].text
            if text:
                return text.strip()
    except Exception:
        pass
    return None


def _fallback_narrative(bundle: EvidenceBundle, query: str) -> str:
    """Human-friendly rule-based summary when LLM is unavailable. Short, readable, with citations [1][2] etc."""
    company_name = ""
    status = ""
    location = ""
    contacts = _contact_names_from_bundle(bundle)
    recent = []

    for i, item in enumerate(bundle.items, 1):
        c = item.content
        if not isinstance(c, dict):
            continue
        if "company_name" in c:
            company_name = c.get("company_name", "")
            ind = c.get("industry_primary") or (c.get("structured_data") or {}).get("industry_primary", "")
            sd = c.get("structured_data") or {}
            city = (c.get("address") or {}).get("city") or sd.get("city", "")
            state = (c.get("address") or {}).get("state") or sd.get("state", "")
            if city or state:
                location = f"{city}, {state}".strip(", ")
            if ind:
                location = f"{ind}; {location}" if location else ind
        elif "current_status" in c or "status" in c:
            status = c.get("current_status") or c.get("status", "N/A")
        elif "subject" in c and len(recent) < 2:
            recent.append(f"[{i}]")
        elif "call_summary" in c and len(recent) < 2:
            recent.append(f"[{i}]")

    sentences = []
    if company_name:
        loc_part = f" ({location})." if location else "."
        sentences.append(f"{company_name} is in {status} status [1][2]{loc_part}")
    elif status:
        sentences.append(f"Current status: {status} [2].")
    else:
        sentences.append("No account summary available.")

    if contacts:
        sentences.append(f"Primary contact(s): {', '.join(contacts)}.")
    if recent:
        sentences.append(f"Recent emails and calls are on record ({', '.join(recent)}).")
    return " ".join(sentences)


def compose_answer(
    bundle: EvidenceBundle,
    query: str = "",
    session_goal: str | None = None,
) -> ComposedAnswer:
    """Build a human-friendly summarized answer, with citations. Uses LLM when GEMINI_API_KEY is set."""
    if not bundle.items:
        return ComposedAnswer(
            narrative="No evidence available for this account.",
            next_steps=None,
            sources=[],
        )
    evidence_text = _evidence_to_prompt_text(bundle)
    narrative = _summarize_with_llm(bundle, query, evidence_text, session_goal)
    if not narrative:
        narrative = _fallback_narrative(bundle, query)
    return ComposedAnswer(
        narrative=narrative,
        next_steps=None,
        sources=[item.source_path or item.source_id for item in bundle.items if item.source_path or item.source_id],
    )
