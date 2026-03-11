"""Unit tests for session goals: set_session_goal validation and goal-biased proactive suggestions."""
from __future__ import annotations

from unittest import TestCase, main

from harper_agent.models import EvidenceBundle, EvidenceItem, SessionState
from harper_agent.proactive_suggestions import (
    FOLLOWUP_REMINDER,
    suggest_follow_ups,
)
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


class TestProactiveSuggestionsOrderByGoal(TestCase):
    """suggest_follow_ups reorders suggestions when session_goal is set."""

    def test_checking_follow_ups_puts_reminder_first(self) -> None:
        bundle = EvidenceBundle(items=[
            EvidenceItem(source_path="account/profile", source_id="a", content={"company_name": "Acme"}),
            EvidenceItem(source_path="account/status", source_id="a", content={"current_status": "awaiting_documents"}),
        ])
        out_no_goal = suggest_follow_ups(bundle, "acct_1", None, session_goal=None)
        out_with_goal = suggest_follow_ups(bundle, "acct_1", None, session_goal="checking_follow_ups")
        self.assertIn(FOLLOWUP_REMINDER, out_with_goal)
        self.assertEqual(out_with_goal[0], FOLLOWUP_REMINDER, "checking_follow_ups should put follow-up reminder first")
        self.assertIn(FOLLOWUP_REMINDER, out_no_goal)

    def test_preparing_outreach_prioritizes_contact(self) -> None:
        bundle = EvidenceBundle(items=[
            EvidenceItem(source_path="account/profile", source_id="a", content={"company_name": "Acme"}),
            EvidenceItem(source_path="account/emails", source_id="e1", content={"subject": "Re: Quote"}),
        ])
        out = suggest_follow_ups(bundle, "acct_1", None, session_goal="preparing_outreach")
        self.assertIn("Want to know who the main contact is?", out)
        self.assertEqual(out[0], "Want to know who the main contact is?", "preparing_outreach should put main contact first")


if __name__ == "__main__":
    main()
