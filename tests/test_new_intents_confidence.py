"""Unit tests for intents, EntityFrame, resolver, and constants."""
from __future__ import annotations

from pathlib import Path
from unittest import TestCase, main

from harper_agent.models import (
    EntityFrame,
    EntityHints,
    EvidenceBundle,
    EvidenceItem,
    PrimaryEntityType,
)
from harper_agent.resolver import resolve


class TestIntentParsing(TestCase):
    """EntityFrame and EntityHints support intent and compare_account_names."""

    def test_entity_frame_has_intent(self) -> None:
        frame = EntityFrame(intent="compare_accounts")
        self.assertEqual(frame.intent, "compare_accounts")
        frame2 = EntityFrame(intent="summarize_activity")
        self.assertEqual(frame2.intent, "summarize_activity")

    def test_entity_hints_compare_account_names(self) -> None:
        hints = EntityHints(compare_account_names=["Acme Corp", "Beta Inc"])
        self.assertEqual(hints.compare_account_names, ["Acme Corp", "Beta Inc"])
        hints_empty = EntityHints()
        self.assertEqual(hints_empty.compare_account_names, [])


class TestResolverCandidateCount(TestCase):
    """Resolver returns (matched, disambig, candidate_count) with correct n_candidates."""

    def test_resolve_returns_three_values(self) -> None:
        frame = EntityFrame(
            primary_entity_type=PrimaryEntityType.ACCOUNT,
            entity_hints=EntityHints(account_name="nonexistent"),
        )
        root = Path(__file__).resolve().parent.parent / "memory"
        # With no matching accounts, matched is [], candidate_count is len(candidate_ids)
        candidate_ids = ["acct_a", "acct_b", "acct_c"]
        matched, disambig, n_candidates = resolve(frame, candidate_ids, root)
        self.assertEqual(len(matched), 0)
        self.assertIsNone(disambig)
        self.assertEqual(n_candidates, 3)


if __name__ == "__main__":
    main()
