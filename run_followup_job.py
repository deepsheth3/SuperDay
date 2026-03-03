#!/usr/bin/env python3
"""Run the Harper follow-up job once: CDC consumer + 3-day/6-day follow-ups (max two)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Load .env from project root
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

from followup_agent.job import run_followup_job


def main() -> None:
    result = run_followup_job()
    print("events_processed:", result["events_processed"])
    print("followup_1_sent:", result["followup_1_sent"])
    print("followup_2_sent:", result["followup_2_sent"])
    if os.environ.get("REDIS_URL"):
        print("(Redis cache enabled)")


if __name__ == "__main__":
    main()
    sys.exit(0)
