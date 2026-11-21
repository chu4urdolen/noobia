"""Unit tests for Noobia log views (task E2 / V1 view follower)."""

import os
from pathlib import Path
import tempfile
import unittest

from views import ViewReader, ViewError, KNOWN_VIEWS


class TestViews(unittest.TestCase):
    def test_known_views_validation(self):
        for v in KNOWN_VIEWS:
            vr = ViewReader(v, backend="fallback")
            self.assertEqual(vr.view, v)

        with self.assertRaises(ViewError):
            ViewReader("BAD VIEW NAME WITH SPACES")

    def test_file_backend_parsing_and_isolation(self):
        with tempfile.NamedTemporaryFile("w+", encoding="utf-8", delete=False) as tf:
            tf.write("Nov 21 14:00:00 lynx user.notice noobia-sense: NOOBIA P1 wifi link.up ssid=Noobia\n")
            tf.write("Nov 21 14:00:01 lynx user.notice noobia-autonomy: NOOBIA P0 autonomy chunk delivered\n")
            tf.write("Nov 21 14:00:02 lynx user.notice noobia-agent: Lynx buzz 100ms\n")
            tf.write("Nov 21 14:00:03 lynx user.notice noobia-sense: NOOBIA P5 touch tap x=10 y=20\n")
            log_path = tf.name

        try:
            reader_sense = ViewReader("noobia-sense", backend="file", log_file=log_path)
            lines_sense = reader_sense.read_recent(10)
            self.assertEqual(len(lines_sense), 2)
            self.assertIn("NOOBIA P1 wifi link.up ssid=Noobia", lines_sense[0])
            self.assertIn("NOOBIA P5 touch tap x=10 y=20", lines_sense[1])

            reader_agent = ViewReader("noobia-agent", backend="file", log_file=log_path)
            lines_agent = reader_agent.read_recent(10)
            self.assertEqual(len(lines_agent), 1)
            self.assertIn("Lynx buzz 100ms", lines_agent[0])
        finally:
            if os.path.exists(log_path):
                os.unlink(log_path)

    def test_read_new_follower(self):
        with tempfile.NamedTemporaryFile("w+", encoding="utf-8", delete=False) as tf:
            tf.write("Nov 21 14:00:00 lynx user.notice noobia-sense: line 1\n")
            tf.flush()
            log_path = tf.name

        try:
            vr = ViewReader("noobia-sense", backend="file", log_file=log_path)
            # First read gets initial line
            first = vr.read_new()
            self.assertEqual(first, ["line 1"])

            # No new lines -> empty list
            second = vr.read_new()
            self.assertEqual(second, [])

            # Append new lines
            with open(log_path, "a", encoding="utf-8") as f:
                f.write("Nov 21 14:00:01 lynx user.notice noobia-sense: line 2\n")
                f.write("Nov 21 14:00:02 lynx user.notice other-tag: ignored\n")
                f.write("Nov 21 14:00:03 lynx user.notice noobia-sense: line 3\n")

            third = vr.read_new()
            self.assertEqual(third, ["line 2", "line 3"])
        finally:
            if os.path.exists(log_path):
                os.unlink(log_path)

    def test_parse_syslog_line(self):
        vr = ViewReader("noobia-sense", backend="fallback")
        raw = "Nov 21 14:00:00 lynx user.notice noobia-sense: NOOBIA P1 wifi link.up"
        payload = vr.parse_syslog_line(raw)
        self.assertEqual(payload, "NOOBIA P1 wifi link.up")

        other = "Nov 21 14:00:00 lynx user.notice noobia-agent: tool executed"
        self.assertIsNone(vr.parse_syslog_line(other))

    def test_f1_split_line_handling(self):
        """F1: Split/half-written line is not consumed until trailing newline arrives."""
        with tempfile.NamedTemporaryFile("wb", delete=False) as tf:
            # Incomplete line
            tf.write(b"Nov 21 14:00:00 lynx user.notice noobia-sense: NOOBIA P1 camera object.seen label=ca")
            tf.flush()
            log_path = tf.name

        try:
            vr = ViewReader("noobia-sense", backend="file", log_file=log_path)
            # Incomplete line must NOT be consumed
            self.assertEqual(vr.read_new(), [])
            self.assertEqual(vr._file_offset, 0)

            # Finish writing the line
            with open(log_path, "ab") as f:
                f.write(b"t\n")

            # Now full line is consumed cleanly
            lines = vr.read_new()
            self.assertEqual(lines, ["NOOBIA P1 camera object.seen label=cat"])
            self.assertGreater(vr._file_offset, 0)
        finally:
            Path(log_path).unlink(missing_ok=True)

    def test_f2_loop_risk_prevention(self):
        """F2: Substring matching removed; quoting another view does not re-enter."""
        with tempfile.NamedTemporaryFile("w+", encoding="utf-8", delete=False) as tf:
            # noobia-autonomy quotes a noobia-sense line: must NOT match noobia-sense view!
            tf.write("Nov 21 14:00:00 lynx user.notice noobia-autonomy: handled sense line noobia-sense: NOOBIA P1 wifi\n")
            # BusyBox [PID] tag format: MUST match
            tf.write("Nov 21 14:00:01 lynx user.notice noobia-sense[995]: NOOBIA P1 wifi link.up\n")
            tf.flush()
            log_path = tf.name

        try:
            vr = ViewReader("noobia-sense", backend="file", log_file=log_path)
            lines = vr.read_new()
            self.assertEqual(len(lines), 1)
            self.assertEqual(lines[0], "NOOBIA P1 wifi link.up")
        finally:
            Path(log_path).unlink(missing_ok=True)

    def test_f3_binary_offsets(self):
        """F3: File is opened in binary mode and tracks exact byte offsets."""
        with tempfile.NamedTemporaryFile("wb", delete=False) as tf:
            log_path = tf.name

        try:
            vr = ViewReader("noobia-sense", backend="file", log_file=log_path)
            # Write line with multi-byte unicode
            msg = "Nov 21 14:00:00 lynx user.notice noobia-sense: NOOBIA P0 ghost 💙\n"
            raw_bytes = msg.encode("utf-8")
            with open(log_path, "wb") as f:
                f.write(raw_bytes)

            lines = vr.read_new()
            self.assertEqual(lines, ["NOOBIA P0 ghost 💙"])
            self.assertEqual(vr._file_offset, len(raw_bytes))
        finally:
            Path(log_path).unlink(missing_ok=True)

    def test_f4_inode_rotation_detection(self):
        """F4: Inode change triggers rotation detection and offset reset."""
        tf = tempfile.NamedTemporaryFile("w+", encoding="utf-8", delete=False)
        tf.write("Nov 21 14:00:00 lynx user.notice noobia-sense: before rotation\n")
        tf.flush()
        log_path = tf.name
        tf.close()

        try:
            vr = ViewReader("noobia-sense", backend="file", log_file=log_path)
            lines1 = vr.read_new()
            self.assertEqual(lines1, ["before rotation"])
            self.assertGreater(vr._file_offset, 0)

            # Rotate: delete old file and recreate with same path (new inode)
            os.unlink(log_path)
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("Nov 21 14:00:01 lynx user.notice noobia-sense: after rotation\n")

            lines2 = vr.read_new()
            self.assertEqual(lines2, ["after rotation"])
        finally:
            Path(log_path).unlink(missing_ok=True)

    def test_journald_probe_on_nexus(self):
        vr = ViewReader("noobia-sense", backend="journald")
        lines = vr.read_recent(5)
        self.assertIsInstance(lines, list)

    def test_state_file_persistence(self):
        """State persistence preserves file offsets across reader restarts."""
        with tempfile.NamedTemporaryFile("w+", encoding="utf-8", delete=False) as tf_log, \
             tempfile.NamedTemporaryFile("w+", delete=False) as tf_state:
            tf_log.write("Nov 21 14:00:00 lynx user.notice noobia-sense: line 1\n")
            tf_log.flush()
            log_path = tf_log.name
            state_path = tf_state.name

        try:
            vr1 = ViewReader("noobia-sense", backend="file", log_file=log_path, state_file=state_path)
            lines1 = vr1.read_new()
            self.assertEqual(lines1, ["line 1"])
            self.assertGreater(vr1._file_offset, 0)

            # Recreate reader with the same state file: offset must be restored
            vr2 = ViewReader("noobia-sense", backend="file", log_file=log_path, state_file=state_path)
            self.assertEqual(vr2._file_offset, vr1._file_offset)
            self.assertEqual(vr2.read_new(), [])

            # Write another line
            with open(log_path, "a", encoding="utf-8") as f:
                f.write("Nov 21 14:00:01 lynx user.notice noobia-sense: line 2\n")

            self.assertEqual(vr2.read_new(), ["line 2"])
        finally:
            Path(log_path).unlink(missing_ok=True)
            Path(state_path).unlink(missing_ok=True)

    def test_journald_no_cursor_starts_at_tail(self):
        """When starting with no cursor, journald starts at tail cursor rather than replaying."""
        vr = ViewReader("noobia-sense", backend="journald")
        vr._journal_cursor = None
        vr._get_journal_tail_cursor = lambda: "mock-tail-cursor-999"

        lines = vr.read_new()
        self.assertEqual(lines, [])
        self.assertEqual(vr._journal_cursor, "mock-tail-cursor-999")


if __name__ == "__main__":
    unittest.main()
