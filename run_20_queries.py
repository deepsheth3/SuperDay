#!/usr/bin/env python3
"""Run the app, open browser at localhost:5050, and feed all 20 queries via the API. Watch the UI (not terminal)."""
from __future__ import annotations

import json
import sys
import threading
import time
import urllib.request
import uuid
import webbrowser

# Avoid running app's __main__ when we import it
if __name__ != "__main__":
    # If imported, just expose QUERIES and a direct run without server
    pass

PORT = 5050
BASE = f"http://127.0.0.1:{PORT}"

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


def _wait_for_server(timeout_sec: float = 30) -> bool:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        try:
            req = urllib.request.Request(BASE + "/", method="GET")
            with urllib.request.urlopen(req, timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.3)
    return False


def _post_message(message: str, session_id: str | None) -> dict:
    data = json.dumps({"message": message, "session_id": session_id or ""}).encode("utf-8")
    req = urllib.request.Request(
        BASE + "/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def _format_reply(payload: dict) -> str:
    reply = payload.get("reply") or ""
    if payload.get("list_items"):
        reply += "\n" + "\n".join("  • " + item for item in payload["list_items"])
    if payload.get("references"):
        reply += "\n\nReferences:\n" + "\n".join(
            "  [{}] {}".format(r.get("num", ""), r.get("label", r.get("source_id", "")))
            for r in payload["references"]
        )
    return reply


def main():
    import os
    os.environ.setdefault("HARPER_MEMORY_ROOT", "memory")

    from app import app

    print("Starting Harper Agent at http://127.0.0.1:{} ...".format(PORT))
    server = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=PORT, use_reloader=False, debug=False),
        daemon=True,
    )
    server.start()

    if not _wait_for_server():
        print("Server did not start in time.", file=sys.stderr)
        sys.exit(1)

    session_id = str(uuid.uuid4())
    print("Opening browser – watch the UI for the conversation.")
    webbrowser.open("{}?session_id={}".format(BASE, session_id))
    time.sleep(1)

    print("Sending 20 queries. After each: 3 sec to read answer, then 2 sec before next. Watch localhost:5050.")
    for i, (label, query) in enumerate(QUERIES, 1):
        try:
            payload = _post_message(query, session_id)
            session_id = payload.get("session_id") or session_id
            if payload.get("error"):
                print("  {}/20 Error: {}".format(i, payload["error"]))
            else:
                print("  {}/20 sent.".format(i))
        except Exception as e:
            print("  {}/20 Request failed: {}".format(i, e))
        if i < len(QUERIES):
            time.sleep(3)   # 3 sec to read the answer
            time.sleep(2)   # 2 sec before next query

    print("Done. App still running at {}. Press Ctrl+C to stop.".format(BASE))
    try:
        server.join()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
