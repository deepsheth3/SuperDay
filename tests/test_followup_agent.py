"""Unit tests for CDC consumer (reset on new communication), follow-up timing, and idempotency."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import TestCase, main

# Use a temp memory root for tests
TEST_MEMORY = Path(__file__).resolve().parent / "_test_memory"


def setUpModule() -> None:
    TEST_MEMORY.mkdir(parents=True, exist_ok=True)
    os.environ["HARPER_MEMORY_ROOT"] = str(TEST_MEMORY)


def tearDownModule() -> None:
    if "HARPER_MEMORY_ROOT" in os.environ and os.environ["HARPER_MEMORY_ROOT"] == str(TEST_MEMORY):
        del os.environ["HARPER_MEMORY_ROOT"]
    import shutil
    if TEST_MEMORY.exists():
        shutil.rmtree(TEST_MEMORY)


class TestCDCConsumerReset(TestCase):
    """CDC consumer must set followup_count=0 and refresh last_activity_at on communication_added."""

    def setUp(self) -> None:
        self.root = TEST_MEMORY
        (self.root / "event_store").mkdir(parents=True, exist_ok=True)
        (self.root / "objects" / "accounts" / "acct_test").mkdir(parents=True, exist_ok=True)

    def test_reset_on_new_communication(self) -> None:
        from followup_agent.state import get_followup_state, reset_followup_on_new_communication, set_followup_state
        set_followup_state("acct_test", followup_count=2, last_activity_at="2020-01-01T00:00:00Z", root=self.root)
        state_before = get_followup_state("acct_test", root=self.root)
        self.assertIsNotNone(state_before)
        self.assertEqual(state_before.get("followup_count"), 2)
        reset_followup_on_new_communication("acct_test", "2025-06-15T12:00:00Z", root=self.root)
        state_after = get_followup_state("acct_test", root=self.root)
        self.assertIsNotNone(state_after)
        self.assertEqual(state_after.get("followup_count"), 0)
        self.assertEqual(state_after.get("last_activity_at"), "2025-06-15T12:00:00Z")

    def test_consumer_processes_communication_added(self) -> None:
        from followup_agent.events import append_event, read_events
        from followup_agent.state import get_followup_state, set_followup_state
        from followup_agent.consumer import process_events
        set_followup_state("acct_test", followup_count=1, last_activity_at="2020-01-01T00:00:00Z", root=self.root)
        append_event("communication_added", "acct_test", {"channel": "email"}, root=self.root)
        n = process_events(root=self.root, limit=10)
        self.assertEqual(n, 1)
        state = get_followup_state("acct_test", root=self.root)
        self.assertIsNotNone(state)
        self.assertEqual(state.get("followup_count"), 0)


class TestFollowupTiming(TestCase):
    """Follow-up: first at 3 days, second at 6 days; never more than 2."""

    def setUp(self) -> None:
        self.root = TEST_MEMORY
        (self.root / "objects" / "accounts" / "acct_timing").mkdir(parents=True, exist_ok=True)
        profile = {"company_name": "Test Co", "email": "client@test.com", "state": "CO", "city": "Denver"}
        (self.root / "objects" / "accounts" / "acct_timing" / "profile.json").write_text(json.dumps(profile))
        (self.root / "objects" / "accounts" / "acct_timing" / "status.json").write_text(
            json.dumps({"current_status": "awaiting_documents"})
        )
        (self.root / "objects" / "accounts" / "acct_timing" / "full.json").write_text(
            json.dumps({"emails": [{"from_address": "client@test.com", "sent_at": "2025-01-01T00:00:00Z"}]})
        )

    def test_followup_count_capped_at_two(self) -> None:
        from followup_agent.state import set_followup_state, get_followup_state
        set_followup_state("acct_timing", followup_count=3, root=self.root)  # invalid
        state = get_followup_state("acct_timing", root=self.root)
        self.assertEqual(state.get("followup_count"), 2)
        set_followup_state("acct_timing", followup_count=0, root=self.root)
        set_followup_state("acct_timing", followup_count=1, root=self.root)
        state = get_followup_state("acct_timing", root=self.root)
        self.assertEqual(state.get("followup_count"), 1)
        set_followup_state("acct_timing", followup_count=2, root=self.root)
        state = get_followup_state("acct_timing", root=self.root)
        self.assertEqual(state.get("followup_count"), 2)


class TestIdempotency(TestCase):
    """Re-running consumer or job must not double-send or double-apply."""

    def setUp(self) -> None:
        self.root = TEST_MEMORY
        (self.root / "event_store").mkdir(parents=True, exist_ok=True)
        (self.root / "objects" / "accounts" / "acct_idem").mkdir(parents=True, exist_ok=True)

    def test_consumer_reset_is_idempotent(self) -> None:
        from followup_agent.events import append_event
        from followup_agent.consumer import process_events
        from followup_agent.state import get_followup_state
        append_event("communication_added", "acct_idem", {"latest_at": "2025-06-01T00:00:00Z"}, root=self.root)
        process_events(root=self.root, limit=10)
        state1 = get_followup_state("acct_idem", root=self.root)
        self.assertIsNotNone(state1)
        self.assertEqual(state1.get("followup_count"), 0)
        # Applying reset again (e.g. re-processing same event) leaves state valid
        from followup_agent.state import reset_followup_on_new_communication
        reset_followup_on_new_communication("acct_idem", "2025-06-01T00:00:00Z", root=self.root)
        state2 = get_followup_state("acct_idem", root=self.root)
        self.assertEqual(state2.get("followup_count"), 0)


if __name__ == "__main__":
    main()
