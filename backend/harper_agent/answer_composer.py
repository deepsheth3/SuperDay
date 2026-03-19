"""Compose a human-friendly summarized answer from evidence, with citations."""
from __future__ import annotations

import os
import re

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from harper_agent.models import ComposedAnswer, EvidenceBundle
from harper_agent import messages as msg


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


def _who_from_email_or_call(item: dict) -> str:
    """Extract 'Harper agent X spoke to Y' style string for evidence so WHO questions can be answered."""
    parts = []
    harper_agent = (
        item.get("harper_rep") or item.get("assigned_agent") or item.get("agent_name")
        or (item.get("sent_by") if isinstance(item.get("sent_by"), str) else None)
    )
    if harper_agent:
        parts.append(f"Harper agent: {harper_agent}")
    contact = item.get("contact_name") or (item.get("to_address") if isinstance(item.get("to_address"), str) else None)
    if contact and "harper" not in (contact or "").lower():
        parts.append(f"contact: {contact}")
    return "; ".join(parts) if parts else ""


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
            agent = c.get("assigned_agent") or c.get("harper_rep") or c.get("harper_rep_id") or ""
            agent_bit = f" Harper rep: {agent}." if agent else ""
            lines.append(f"[{i}] Account: {name} — {ind}; {city}, {state}.{agent_bit}")
        elif "current_status" in c or "status" in c:
            lines.append(f"[{i}] Status: {c.get('current_status') or c.get('status', 'N/A')}.")
        elif "subject" in c:
            who = _who_from_email_or_call(c)
            extra = f" — {who}" if who else ""
            lines.append(f"[{i}] Email: {c.get('subject', '')} ({c.get('sent_at', '')}){extra}.")
        elif "call_summary" in c:
            who = _who_from_email_or_call(c)
            extra = f" — {who}" if who else ""
            lines.append(f"[{i}] Call: {c.get('call_summary', '')} — contact: {c.get('contact_name', 'N/A')}{extra} ({c.get('started_at', '')}).")
        else:
            lines.append(f"[{i}] {str(c)[:150]}.")
    return "\n".join(lines) if lines else msg.MSG_NO_EVIDENCE_LINES


def _summarize_with_llm(
    bundle: EvidenceBundle,
    query: str,
    evidence_text: str,
    session_goal: str | None = None,
) -> str | None:
    """Use Gemini to produce a short, human-friendly summary. Returns None on failure."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        prompt = f"""Summarize the following evidence to answer the user's question. Write in plain language, 2–4 sentences. No citation numbers or references. No raw data dumps.

Evidence:
{evidence_text}

User question: {query or 'Summarize this account.'}

Write only the summary."""

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


def _summarize_with_llm_stream(
    bundle: EvidenceBundle,
    query: str,
    evidence_text: str,
    session_goal: str | None = None,
):
    """Yield text chunks from Gemini streaming API. Yields nothing and returns None on failure."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        prompt = f"""Summarize the following evidence to answer the user's question. Plain language, 2–4 sentences. No citation numbers or references.

Evidence:
{evidence_text}

User question: {query or 'Summarize this account.'}

Write only the summary."""

        stream = getattr(client.models, "generate_content_stream", None)
        if not stream:
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=500),
            )
            text = getattr(response, "text", None) or (response.candidates[0].content.parts[0].text if getattr(response, "candidates", None) else None)
            if text:
                yield text.strip()
            return
        for chunk in client.models.generate_content_stream(
            model="gemini-2.0-flash",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=500),
        ):
            text = getattr(chunk, "text", None)
            if not text and getattr(chunk, "candidates", None) and chunk.candidates:
                c = chunk.candidates[0]
                if getattr(c, "content", None) and c.content.parts:
                    text = c.content.parts[0].text
            if text:
                yield text
    except Exception:
        pass


def compose_answer_stream(
    bundle: EvidenceBundle,
    query: str = "",
    session_goal: str | None = None,
):
    """Yield narrative chunks (streaming). Caller joins to get full narrative; falls back to non-streaming if no stream support."""
    if not bundle.items:
        yield _fallback_narrative(bundle, query)
        return
    evidence_text = _evidence_to_prompt_text(bundle)
    chunks = []
    for c in _summarize_with_llm_stream(bundle, query, evidence_text, session_goal):
        chunks.append(c)
        yield c
    if not chunks:
        yield _fallback_narrative(bundle, query)


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
        sentences.append(msg.MSG_FALLBACK_STATUS.format(status=status))
    else:
        sentences.append(msg.MSG_FALLBACK_NO_SUMMARY)

    if contacts:
        sentences.append(msg.MSG_FALLBACK_PRIMARY_CONTACTS.format(contacts=", ".join(contacts)))
    if recent:
        sentences.append(msg.MSG_FALLBACK_RECENT_ON_RECORD.format(refs=", ".join(recent)))
    return " ".join(sentences)


def _strip_citation_refs(text: str) -> str:
    """Remove trailing citation refs like ' [7, 8].' or ' [1]' so the user never sees them."""
    if not text or not text.strip():
        return text
    s = text.strip()
    # Strip ref at end, optionally followed by period; keep sentence-ending period if present
    out = re.sub(r"\s*\[\d+(?:\s*,\s*\d+)*\]\.?\s*$", "", s).strip()
    if out and s.rstrip().endswith(".") and not out.endswith("."):
        out = out + "."
    return out or text


def compose_answer(
    bundle: EvidenceBundle,
    query: str = "",
    session_goal: str | None = None,
) -> ComposedAnswer:
    """Build a human-friendly summarized answer, with citations. Uses LLM when GEMINI_API_KEY is set."""
    if not bundle.items:
        return ComposedAnswer(
            narrative=msg.MSG_NO_EVIDENCE,
            next_steps=None,
            sources=[],
        )
    evidence_text = _evidence_to_prompt_text(bundle)
    try:
        narrative = _summarize_with_llm(bundle, query, evidence_text, session_goal)
    except Exception:
        narrative = None
    if not narrative:
        narrative = _fallback_narrative(bundle, query)
    narrative = _strip_citation_refs(narrative or "")
    return ComposedAnswer(
        narrative=narrative,
        next_steps=None,
        sources=[item.source_path or item.source_id for item in bundle.items if item.source_path or item.source_id],
    )
