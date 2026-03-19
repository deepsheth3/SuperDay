#!/usr/bin/env python3
"""Run sample test queries and print outputs. Use one session for session-aware flow."""
from __future__ import annotations

import sys
import os
from pathlib import Path

_cs = Path(__file__).resolve().parent / "backend"
if str(_cs) not in sys.path:
    sys.path.insert(0, str(_cs))

from harper_agent.main import run_agent_loop

SESSION = "sample-session"

QUERIES = [
    # --- Specific / single-account ---
    ("Specific: status with location", "What is the status of Evergreen Public Services in Austin CO?"),
    ("Specific: account by name", "Tell me about Harborline Hotel Group Inc."),
    ("Specific: accounts in a state", "Which accounts are in Colorado?"),
    # --- Session-aware: Company A -> Company B -> "from that" = B ---
    ("[1] Company A", "What is the status of Evergreen Public Services in Austin CO?"),
    ("[2] Company B (switch)", "Tell me about Harborline Hotel Group Inc."),
    ("[3] Session: from that, who was the contact?", "From that company, who was the person of contact?"),
    ("[4] Session: status of that one", "What is the status of that one?"),
    # --- More session references ---
    ("[5] Session: contact for that", "Who was the contact for that?"),
]


def main():
    _repo = Path(__file__).resolve().parent
    os.environ.setdefault("HARPER_MEMORY_ROOT", str(_repo / "memory"))
    print("=" * 70)
    print("HARPER AGENT – SAMPLE QUERIES & OUTPUTS")
    print("=" * 70)
    for label, query in QUERIES:
        print(f"\n--- {label} ---")
        print(f"Query: {query!r}")
        result = run_agent_loop(SESSION, query)
        narrative = result["narrative"]
        if result.get("list_items"):
            narrative += "\n" + "\n".join("  • " + item for item in result["list_items"])
        if result.get("references"):
            narrative += "\n\nReferences:\n" + "\n".join(
                "  [{}] {}".format(r["num"], r.get("label", r.get("source_id", ""))) for r in result["references"]
            )
        out = narrative if len(narrative) <= 600 else narrative[:597] + "..."
        print(f"Reply:\n{out}")
    print("\n" + "=" * 70)
    print("Done. Start the API: cd backend && uvicorn app.main:app --port 8080")
    print("Frontend: http://localhost:3000 — set NEXT_PUBLIC_API_URL=http://localhost:8080")
    print("=" * 70)


if __name__ == "__main__":
    main()
