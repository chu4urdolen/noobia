"""Unit tests for :mod:`projects.solo_dashboard.timeline`.

The tests exercise a variety of realistic Codex JSONL snippets to verify that
``visible_messages`` correctly filters out non‑public records and preserves
order.  The test data is embedded directly in the file to avoid external
dependencies.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from projects.solo_dashboard.timeline import visible_messages


class TestVisibleMessages(unittest.TestCase):
    def _make_log(self, records):
        """Return a temporary file path containing *records* as JSONL.

        Parameters
        ----------
        records:
            Iterable of dicts to be written one per line.
        """

        f = tempfile.NamedTemporaryFile("w", delete=False, suffix=".jsonl")
        for r in records:
            f.write(json.dumps(r) + "\n")
        f.close()
        return f.name

    def test_simple_conversation(self):
        """A short conversation with one user and one assistant turn."""
        records = [
            {
                "type": "response_item",
                "timestamp": 1,
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": {"type": "input_text", "text": "Hi"},
                },
            },
            {
                "type": "response_item",
                "timestamp": 2,
                "item": {
                    "type": "message",
                    "role": "assistant",
                    "content": {"type": "output_text", "text": "Hello"},
                },
            },
        ]
        path = self._make_log(records)
        try:
            out = visible_messages(path)
            self.assertEqual(len(out), 2)
            self.assertEqual(out[0]["role"], "user")
            self.assertEqual(out[0]["text"], "Hi")
            self.assertEqual(out[1]["role"], "assistant")
            self.assertEqual(out[1]["text"], "Hello")
        finally:
            os.unlink(path)

    def test_ignores_non_public(self):
        """Non‑public records are excluded from the output."""
        records = [
            {
                "type": "response_item",
                "timestamp": 1,
                "item": {
                    "type": "message",
                    "role": "assistant",
                    "content": {"type": "output_text", "text": "Step 1"},
                },
            },
            {
                # A tool call – should be ignored
                "type": "response_item",
                "timestamp": 2,
                "item": {
                    "type": "tool_call",
                    "role": "assistant",
                    "content": {"type": "output_text", "text": "Calling"},
                },
            },
            {
                # A reasoning step – should be ignored
                "type": "response_item",
                "timestamp": 3,
                "item": {
                    "type": "message",
                    "role": "assistant",
                    "content": {"type": "output_text", "text": "Thinking"},
                },
            },
        ]
        path = self._make_log(records)
        try:
            out = visible_messages(path)
            # Only the first assistant message is public
            self.assertEqual(len(out), 1)
            self.assertEqual(out[0]["role"], "assistant")
            self.assertEqual(out[0]["text"], "Step 1")
        finally:
            os.unlink(path)

    def test_order_preserved(self):
        """The function preserves the order of visible messages."""
        records = [
            {
                "type": "response_item",
                "timestamp": 1,
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": {"type": "input_text", "text": "First"},
                },
            },
            {
                "type": "response_item",
                "timestamp": 2,
                # Non‑public – ignored
                "item": {"type": "tool_call", "role": "assistant", "content": {"type": "output_text", "text": "Tool"}},
            },
            {
                "type": "response_item",
                "timestamp": 3,
                "item": {
                    "type": "message",
                    "role": "assistant",
                    "content": {"type": "output_text", "text": "Second"},
                },
            },
        ]
        path = self._make_log(records)
        try:
            out = visible_messages(path)
            self.assertEqual([m["text"] for m in out], ["First", "Second"])
        finally:
            os.unlink(path)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

