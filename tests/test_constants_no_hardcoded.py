"""Unit tests: intent/goal validation and status set membership (no query-specific regex, no hardcoded logic)."""
from __future__ import annotations

from unittest import TestCase, main

from harper_agent.constants import (
    ALLOWED_SESSION_GOALS,
    INTENT_VALUES,
    WAITING_ON_CLIENT_STATUSES,
    get_confirm_binding_statuses,
    get_waiting_on_client_statuses,
    normalize_status_key,
)
from harper_agent.models import EvidenceBundle, EvidenceItem
from harper_agent.proactive_suggestions import FOLLOWUP_REMINDER, suggest_follow_ups


class TestIntentAndGoalFromConstants(TestCase):
    """Intent and session goal validation use constants, not hardcoded tuples."""

    def test_intent_values_contains_expected(self) -> None:
        self.assertIn("status_query", INTENT_VALUES)
        self.assertIn("compare_accounts", INTENT_VALUES)
        self.assertIn("unknown", INTENT_VALUES)

    def test_allowed_session_goals_contains_expected(self) -> None:
        self.assertIn("checking_follow_ups", ALLOWED_SESSION_GOALS)
        self.assertIn("preparing_outreach", ALLOWED_SESSION_GOALS)


class TestFollowupSuggestionUsesStatusSetMembership(TestCase):
    """Follow-up reminder suggestion uses WAITING_ON_CLIENT_STATUSES membership, not substring."""

    def test_status_in_set_adds_followup_reminder(self) -> None:
        bundle = EvidenceBundle(items=[
            EvidenceItem(
                source_path="account/status",
                source_id="a",
                content={"current_status": "awaiting_documents"},
            ),
        ])
        out = suggest_follow_ups(bundle, "acct_1", None)
        self.assertIn(FOLLOWUP_REMINDER, out)

    def test_status_not_in_set_does_not_add_followup_reminder(self) -> None:
        bundle = EvidenceBundle(items=[
            EvidenceItem(
                source_path="account/status",
                source_id="a",
                content={"current_status": "policy_bound"},
            ),
        ])
        out = suggest_follow_ups(bundle, "acct_1", None)
        self.assertNotIn(FOLLOWUP_REMINDER, out)

    def test_normalize_status_key_matches_set(self) -> None:
        self.assertEqual(normalize_status_key("awaiting_documents"), "awaiting_documents")
        self.assertIn(normalize_status_key("Awaiting Documents"), WAITING_ON_CLIENT_STATUSES)


class TestWaitingUsesSharedConstants(TestCase):
    """followup_agent.waiting uses shared WAITING_ON_CLIENT_STATUSES from constants."""

    def test_waiting_imports_same_statuses(self) -> None:
        from followup_agent import waiting

        self.assertIs(waiting.WAITING_ON_CLIENT_STATUSES, WAITING_ON_CLIENT_STATUSES)

    def test_get_waiting_on_client_returns_default_set(self) -> None:
        default = get_waiting_on_client_statuses(None)
        self.assertEqual(default, WAITING_ON_CLIENT_STATUSES)
        self.assertIn("awaiting_documents", default)
        self.assertIn("contacted_by_harper", default)


class TestConfirmStatusSets(TestCase):
    """Confirm next steps and binding use status sets, not substrings."""

    def test_confirm_binding_statuses_contains_expected(self) -> None:
        default = get_confirm_binding_statuses(None)
        self.assertIn("policy_bound", default)
        self.assertIn("bound", default)
