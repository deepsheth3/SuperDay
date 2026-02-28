#!/usr/bin/env python3
"""Run sample test queries and print outputs. Use one session for session-aware flow."""
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
    print("=" * 70)
    print("HARPER AGENT – SAMPLE QUERIES & OUTPUTS")
    print("=" * 70)
    for label, query in QUERIES:
        print(f"\n--- {label} ---")
        print(f"Query: {query!r}")
        reply = run_agent_loop(SESSION, query)
        # Truncate long replies for readability
        out = reply if len(reply) <= 600 else reply[:597] + "..."
        print(f"Reply:\n{out}")
    print("\n" + "=" * 70)
    print("Done. Start the UI with: python app.py")
    print("Then open http://127.0.0.1:5050 and try the same queries.")
    print("=" * 70)

if __name__ == "__main__":
    main()
