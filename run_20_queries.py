#!/usr/bin/env python3
"""Run all 20 mixed test queries in sequence. Uses one session so session-aware queries (7–11, 17, 19) get context."""
from harper_agent.main import run_agent_loop

SESSION = "20-queries-session"

QUERIES = [
    # 1. Very specific (6)
    ("1. Specific", "What is the status of Evergreen Public Services in Austin CO?"),
    ("2. Specific", "Tell me about Harborline Hotel Group Inc."),
    ("3. Specific", "Who is the contact for Skyline Protective Services in North Carolina?"),
    ("4. Specific", "What's the status of Summerside Child Care in Houston Pennsylvania?"),
    ("5. Specific", "Give me the status of Lone Star Child Care Center in Colorado."),
    ("6. Specific", "Tell me about Harborline Hotel Group in Austin Massachusetts."),
    # 2. Session-aware (5) – "that" = last account from above
    ("7. Session", "From that company, who was the person of contact?"),
    ("8. Session", "What is the status of that one?"),
    ("9. Session", "Who was the contact for that?"),
    ("10. Session", "Tell me more about that account."),
    ("11. Session", "What happened with that application?"),
    # 3. List / filter (5)
    ("12. List", "Which accounts are in Colorado?"),
    ("13. List", "List all public sector accounts."),
    ("14. List", "Which accounts are awaiting documents?"),
    ("15. List", "Show me hospitality accounts that are policy bound."),
    ("16. List", "Retail accounts which require documents."),
    # 4. Conversational / vague (4) – 17/19 use "that" (session); 18/20 by industry+location
    ("17. Vague", "What happened to that childcare center in California?"),
    ("18. Vague", "Hey, what's going on with the hotel group in Austin?"),
    ("19. Vague", "Any updates on the public sector account we were looking at?"),
    ("20. Vague", "What about the defense contractor in Chicago?"),
]

def main():
    print("=" * 72)
    print("20 MIXED QUERIES – specific, session-aware, list, vague")
    print("=" * 72)
    for label, query in QUERIES:
        print(f"\n--- {label}: {query[:60]}{'...' if len(query) > 60 else ''} ---")
        reply = run_agent_loop(SESSION, query)
        out = reply if len(reply) <= 400 else reply[:397] + "..."
        print(out)
    print("\n" + "=" * 72)

if __name__ == "__main__":
    main()
