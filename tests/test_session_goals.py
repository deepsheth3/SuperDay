"""Unit tests for session goals: set_session_goal validation."""
from __future__ import annotations

from unittest import TestCase, main

from harper_agent.models import SessionState
from harper_agent.session_manager import set_session_goal


class TestSetSessionGoal(TestCase):
    """set_session_goal validates and sets or clears session_goal."""

    def test_set_valid_goal(self) -> None:
        state = SessionState(session_id="t1")
        set_session_goal(state, "checking_follow_ups")
        self.assertEqual(state.session_goal, "checking_follow_ups")
        set_session_goal(state, "preparing_outreach")
        self.assertEqual(state.session_goal, "preparing_outreach")

    def test_invalid_goal_cleared(self) -> None:
        state = SessionState(session_id="t2", session_goal="triaging_pipeline")
        set_session_goal(state, "invalid_goal")
        self.assertIsNone(state.session_goal)

    def test_none_clears_goal(self) -> None:
        state = SessionState(session_id="t3", session_goal="reviewing_one_account")
        set_session_goal(state, None)
        self.assertIsNone(state.session_goal)

    def test_empty_string_clears_goal(self) -> None:
        state = SessionState(session_id="t4", session_goal="checking_follow_ups")
        set_session_goal(state, "   ")
        self.assertIsNone(state.session_goal)


if __name__ == "__main__":
    main()
