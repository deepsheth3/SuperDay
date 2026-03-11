"""Tests for MemGPT-style components: recall search, queue manager, function executor, working context."""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import TestCase

from harper_agent.function_executor import (
    execute_tool,
    parse_llm_output,
)
from harper_agent.models import SessionState
from harper_agent.queue_manager import (
    estimate_tokens,
    evict_oldest_messages,
    should_evict,
    should_inject_memory_pressure,
)
from harper_agent.session_manager import (
    working_context_append,
    working_context_get,
    working_context_replace,
)
from harper_agent.transcript_service import (
    append_turn,
    get_transcript,
    recall_storage_search,
)


class TestEstimateTokens(TestCase):
    def test_estimate_tokens(self) -> None:
        self.assertEqual(estimate_tokens(""), 0)
        self.assertEqual(estimate_tokens("abcd"), 1)
        self.assertEqual(estimate_tokens("a" * 8), 2)


class TestQueueManager(TestCase):
    def test_should_inject_memory_pressure(self) -> None:
        from harper_agent.models import TurnRecord

        state = SessionState(session_id="q1", working_context="x" * 100)
        state.turn_history = [TurnRecord(role="user", message="hi"), TurnRecord(role="assistant", message="hello")]
        # Small context: no pressure
        self.assertFalse(should_inject_memory_pressure(state, "system", max_tokens=8000))
        # Huge system + many turns: pressure
        state.turn_history = [TurnRecord(role="user", message="x" * 2000)] * 20
        self.assertTrue(should_inject_memory_pressure(state, "x" * 10000, max_tokens=8000))

    def test_should_evict(self) -> None:
        from harper_agent.models import TurnRecord

        state = SessionState(session_id="q2")
        state.turn_history = [TurnRecord(role="user", message="a" * 500)] * 80
        self.assertTrue(should_evict(state, "sys" * 1000, max_tokens=8000))

    def test_evict_oldest_messages(self) -> None:
        from harper_agent.models import TurnRecord

        state = SessionState(session_id="q3", rolling_summary="")
        state.turn_history = []
        for i in range(10):
            state.turn_history.append(TurnRecord(role="user", message=f"msg{i}"))
            state.turn_history.append(TurnRecord(role="assistant", message=f"reply{i}"))
        # Force eviction by using tiny max_tokens
        evicted = evict_oldest_messages(state, system_prompt="x" * 5000, max_tokens=100)
        self.assertGreater(len(evicted), 0)
        self.assertLess(len(state.turn_history), 20)
        self.assertTrue(len(state.rolling_summary) > 0 or len(evicted) > 0)


class TestParseLlmOutput(TestCase):
    def test_plain_message(self) -> None:
        kind, msg, args, hb = parse_llm_output("Hello, here is my reply.")
        self.assertEqual(kind, "message")
        self.assertEqual(msg, "Hello, here is my reply.")
        self.assertIsNone(args)
        self.assertFalse(hb)

    def test_function_call_json_block(self) -> None:
        text = 'Some text\n```json\n{"function": "recall_storage.search", "arguments": {"query": "six flags"}, "request_heartbeat": true}\n```'
        kind, name, args, hb = parse_llm_output(text)
        self.assertEqual(kind, "function_call")
        self.assertEqual(name, "recall_storage.search")
        self.assertEqual(args.get("query"), "six flags")
        self.assertTrue(hb)

    def test_send_message(self) -> None:
        text = '```json\n{"function": "send_message", "arguments": {"message": "Done!"}}\n```'
        kind, name, args, hb = parse_llm_output(text)
        self.assertEqual(kind, "function_call")
        self.assertEqual(name, "send_message")
        self.assertEqual(args.get("message"), "Done!")


class TestWorkingContextTools(TestCase):
    def test_append_and_get(self) -> None:
        state = SessionState(session_id="w1")
        working_context_append(state, "User prefers email.")
        self.assertIn("email", working_context_get(state))
        working_context_append(state, "Current account: acct_123")
        content = working_context_get(state)
        self.assertIn("email", content)
        self.assertIn("acct_123", content)

    def test_replace(self) -> None:
        state = SessionState(session_id="w2", working_context="Account is acct_old. Status: pending.")
        working_context_replace(state, "acct_old", "acct_new")
        self.assertIn("acct_new", state.working_context)
        self.assertNotIn("acct_old", state.working_context)


class TestRecallStorageSearch(TestCase):
    def test_recall_search_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "transcripts").mkdir()
            # No file yet
            snippets, total = recall_storage_search(
                "nosuch_session",
                root=root,
            )
            self.assertEqual(total, 0)
            self.assertEqual(snippets, [])

    def test_recall_search_with_turns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "transcripts").mkdir(parents=True)
            session_id = "recall_test_1"
            append_turn(session_id, "user", "What is the status?", root=root)
            append_turn(session_id, "assistant", "The status is active.", root=root)
            append_turn(session_id, "user", "Tell me about six flags", root=root)
            snippets, total = recall_storage_search(session_id, "", root=root)
            self.assertEqual(total, 3)
            self.assertEqual(len(snippets), 3)
            snippets, total = recall_storage_search(session_id, "six flags", root=root)
            self.assertEqual(total, 1)
            self.assertIn("six flags", snippets[0].lower())


class TestExecuteTool(TestCase):
    def test_working_context_append_via_tool(self) -> None:
        state = SessionState(session_id="e1")
        ctx = {"session_id": "e1", "state": state, "tenant_id": None, "root": None}
        result = execute_tool("working_context.append", {"text": "Key: value"}, ctx)
        self.assertIn("Appended", result)
        self.assertIn("value", working_context_get(state))

    def test_working_context_get_via_tool(self) -> None:
        state = SessionState(session_id="e2", working_context="Stored fact.")
        ctx = {"session_id": "e2", "state": state}
        result = execute_tool("working_context.get", {}, ctx)
        self.assertEqual(result, "Stored fact.")

    def test_unknown_tool_raises(self) -> None:
        ctx = {"session_id": "e3", "state": SessionState(session_id="e3")}
        with self.assertRaises(ValueError):
            execute_tool("unknown_tool", {}, ctx)
