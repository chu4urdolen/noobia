"""Tests for common/autonomy/events.py (NA-10)."""

import os
import tempfile
import unittest
from pathlib import Path

from common.autonomy.events import EventStore


class TestEventStore(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "test_events.db"
        self.store = EventStore(self.db_path, noob_name="testlynx", boot_id="boot01")

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_capture_and_generate_ids(self):
        e1 = self.store.capture("NOOBIA P1 touch tap", origin="lynx", priority=1)
        e2 = self.store.capture("NOOBIA P0 wifi scan", origin="lynx", priority=0)
        self.assertEqual(e1.event_id, "testlynx-boot01-00000001")
        self.assertEqual(e2.event_id, "testlynx-boot01-00000002")
        self.assertEqual(e1.state, "captured")

    def test_ignore_rule(self):
        e = self.store.capture("NOOBIA P1 touch rapid", origin="lynx")
        self.store.mark_ignored(e.event_id, reason="debounce")
        counts = self.store.count_by_state()
        self.assertEqual(counts.get("ignored"), 1)

    def test_delivery_and_ack_lifecycle(self):
        e1 = self.store.capture("event 1", origin="lynx")
        e2 = self.store.capture("event 2", origin="lynx")
        pending = self.store.get_pending()
        self.assertEqual(len(pending), 2)

        # Deliver in batch
        self.store.mark_delivered([e1.event_id, e2.event_id], batch_id="batch_42")
        counts = self.store.count_by_state()
        self.assertEqual(counts.get("delivered"), 2)

        # Worker completes and acks
        self.store.ack([e1.event_id, e2.event_id])
        counts_after = self.store.count_by_state()
        self.assertEqual(counts_after.get("acked"), 2)
        self.assertEqual(len(self.store.get_pending()), 0)


if __name__ == "__main__":
    unittest.main()
