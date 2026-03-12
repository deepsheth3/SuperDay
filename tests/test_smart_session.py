"""Unit tests for smart session history: turn cap, rolling summary, recent_entities cap."""
from __future__ import annotations

from unittest import TestCase, main

from harper_agent.models import SessionState
from harper_agent.session_manager import (
    append_turn,
    get_session,
    update_recent_entities,
    set_last_intent_constraints,
    MAX_RECENT_ACCOUNT_IDS,
    MAX_RECENT_PERSON_IDS,
    MAX_RECENT_TURNS,
    MAX_ROLLING_SUMMARY_WORDS,
)


class TestSmartSessionTurnCap(TestCase):
    """turn_history is capped at MAX_RECENT_TURNS; dropped turns feed rolling_summary."""

    def test_turn_cap_and_rolling_summary(self) -> None:
        state = SessionState(session_id="test-cap")
        for i in range(MAX_RECENT_TURNS + 2):
            append_turn(
                state,
                "user" if i % 2 == 0 else "assistant",
                f"message {i}",
                resolved_account_id=f"acct_{i}" if i % 2 == 1 else None,
            )
        self.assertEqual(len(state.turn_history), MAX_RECENT_TURNS, "turn_history should be capped at MAX_RECENT_TURNS")
        self.assertTrue(
            bool(state.rolling_summary.strip()),
            "rolling_summary should be non-empty after dropping turns",
        )
        self.assertLessEqual(
            len(state.rolling_summary.split()),
            MAX_ROLLING_SUMMARY_WORDS,
            "rolling_summary should be word-capped",
        )


class TestSmartSessionRecentEntities(TestCase):
    """recent_account_ids and recent_person_ids are capped and most recent last."""

    def test_recent_account_ids_cap_and_order(self) -> None:
        state = SessionState(session_id="test-accounts")
        for i in range(7):
            update_recent_entities(state, account_id=f"acct_{i}")
        self.assertEqual(len(state.recent_account_ids), MAX_RECENT_ACCOUNT_IDS)
        self.assertEqual(state.recent_account_ids[-1], "acct_6", "most recent should be last")
        self.assertEqual(state.recent_account_ids[0], "acct_2", "oldest of the 5 should be first")

    def test_recent_person_ids_cap(self) -> None:
        state = SessionState(session_id="test-persons")
        update_recent_entities(state, person_id="person_a")
        update_recent_entities(state, person_id="person_b")
        self.assertEqual(state.recent_person_ids, ["person_a", "person_b"])
        for i in range(5):
            update_recent_entities(state, person_id=f"person_{i}")
        self.assertEqual(len(state.recent_person_ids), MAX_RECENT_PERSON_IDS)

    def test_recent_entities_dedupe(self) -> None:
        state = SessionState(session_id="test-dedupe")
        update_recent_entities(state, account_id="acct_x")
        update_recent_entities(state, account_id="acct_y")
        update_recent_entities(state, account_id="acct_x")  # move x to end
        self.assertEqual(state.recent_account_ids, ["acct_y", "acct_x"])


class TestSmartSessionIntentConstraints(TestCase):
    """set_last_intent_constraints stores intent and constraints."""

    def test_set_last_intent_constraints(self) -> None:
        state = SessionState(session_id="test-intent")
        set_last_intent_constraints(state, "list_accounts", {"state": "CO", "industry": "public_sector"})
        self.assertEqual(state.last_intent, "list_accounts")
        self.assertEqual(state.last_constraints, {"state": "CO", "industry": "public_sector"})
        set_last_intent_constraints(state, None, None)
        self.assertIsNone(state.last_intent)
        self.assertEqual(state.last_constraints, {})


if __name__ == "__main__":
    main()
