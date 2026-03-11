"""Unit tests for new intents, confidence-aware prefix, and proactive follow-up suggestions."""
from __future__ import annotations

import json
from pathlib import Path
from unittest import TestCase, main

from harper_agent.models import (
    EntityFrame,
    EntityHints,
    EntityConstraints,
    EntityReference,
    EvidenceBundle,
    EvidenceItem,
    PrimaryEntityType,
)
from harper_agent.proactive_suggestions import suggest_follow_ups
from harper_agent.resolver import resolve
from harper_agent.intent_handlers import handle_suggest_next_action


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


class TestProactiveSuggestions(TestCase):
    """suggest_follow_ups returns rule-based suggestions from bundle and status."""

    def test_suggestions_when_has_emails_or_calls(self) -> None:
        bundle = EvidenceBundle(items=[
            EvidenceItem(source_path="account/emails", source_id="e1", content={"subject": "Re: Quote"}),
        ])
        out = suggest_follow_ups(bundle, "acct_1", None)
        self.assertIn("Want to see the latest email or call?", out)

    def test_suggestions_when_awaiting_documents(self) -> None:
        bundle = EvidenceBundle(items=[
            EvidenceItem(source_path="account/status", source_id="acct_1", content={"current_status": "awaiting_documents"}),
        ])
        out = suggest_follow_ups(bundle, "acct_1", None)
        self.assertIn("I can suggest a follow-up reminder.", out)

    def test_suggestions_when_has_profile(self) -> None:
        bundle = EvidenceBundle(items=[
            EvidenceItem(source_path="account/profile", source_id="acct_1", content={"company_name": "Acme"}),
        ])
        out = suggest_follow_ups(bundle, "acct_1", None)
        self.assertIn("Want to know who the main contact is?", out)

    def test_suggestions_capped_at_three(self) -> None:
        bundle = EvidenceBundle(items=[
            EvidenceItem(source_path="account/profile", source_id="a", content={}),
            EvidenceItem(source_path="account/status", source_id="a", content={"status": "awaiting_documents"}),
            EvidenceItem(source_path="account/emails", source_id="e1", content={}),
        ])
        out = suggest_follow_ups(bundle, "acct_1", None)
        self.assertLessEqual(len(out), 3)


class TestSuggestNextActionHandler(TestCase):
    """handle_suggest_next_action returns rule-based next step from status."""

    def test_awaiting_documents_suggests_followup(self) -> None:
        root = Path(__file__).resolve().parent.parent
        mem = root / "memory"
        mem.mkdir(parents=True, exist_ok=True)
        acct_dir = mem / "objects" / "accounts" / "acct_suggest_test"
        acct_dir.mkdir(parents=True, exist_ok=True)
        (acct_dir / "profile.json").write_text(json.dumps({"company_name": "Test"}), encoding="utf-8")
        (acct_dir / "status.json").write_text(
            json.dumps({"current_status": "awaiting_documents"}), encoding="utf-8"
        )
        try:
            out = handle_suggest_next_action("acct_suggest_test", "What should I do?", mem)
            self.assertIn("follow-up", out.lower())
        finally:
            if acct_dir.exists():
                for f in acct_dir.iterdir():
                    f.unlink()
                acct_dir.rmdir()


if __name__ == "__main__":
    main()
