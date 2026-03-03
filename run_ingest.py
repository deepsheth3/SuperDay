#!/usr/bin/env python3
"""Run ingest: read harper_accounts.jsonl, write memory/objects/ and indices, emit CDC events."""
from __future__ import annotations

import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

from followup_agent.ingest import ingest_jsonl


def main() -> None:
    path = Path(__file__).resolve().parent / "harper_accounts.jsonl"
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
    count = ingest_jsonl(path=path, emit_cdc=True)
    print(f"Ingested {count} accounts. CDC events written to memory/event_store/events.jsonl.")


if __name__ == "__main__":
    main()
    sys.exit(0)
