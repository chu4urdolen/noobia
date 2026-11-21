"""Unit tests for Noobia log views (task E2)."""

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

    def test_parse_syslog_line(self):
        vr = ViewReader("noobia-sense", backend="fallback")
        raw = "Nov 21 14:00:00 lynx user.notice noobia-sense: NOOBIA P1 wifi link.up"
        payload = vr.parse_syslog_line(raw)
        self.assertEqual(payload, "NOOBIA P1 wifi link.up")

        other = "Nov 21 14:00:00 lynx user.notice noobia-agent: tool executed"
        self.assertIsNone(vr.parse_syslog_line(other))

    def test_journald_probe_on_nexus(self):
        # Read-only live test on Nexus journald
        vr = ViewReader("noobia-sense", backend="journald")
        lines = vr.read_recent(5)
        # Should execute cleanly without raising an exception
        self.assertIsInstance(lines, list)


if __name__ == "__main__":
    unittest.main()
