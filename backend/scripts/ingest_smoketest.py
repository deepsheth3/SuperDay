#!/usr/bin/env python3
"""POST a sample ingest to the running API (default http://127.0.0.1:8080)."""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
import uuid


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", default="http://127.0.0.1:8080")
    p.add_argument("--tenant-id", default="550e8400-e29b-41d4-a716-446655440000")
    args = p.parse_args()

    body = {
        "tenant_id": args.tenant_id,
        "source_system": "smoketest",
        "source_event_id": str(uuid.uuid4()),
        "raw_payload_ref": "",
        "raw_body_text": "Hello from ingest_smoketest.py — replace tenant_id with a row from tenants table.",
        "subject": "Smoke test",
    }
    req = urllib.request.Request(
        f"{args.base_url.rstrip('/')}/api/ingest/email",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            out = json.loads(r.read().decode())
            print(json.dumps(out, indent=2))
            eid = out.get("event_id")
            if eid:
                print(f"\nPoll: GET {args.base_url}/api/pipeline/events/{eid}")
    except urllib.error.HTTPError as e:
        print(e.read().decode(), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
