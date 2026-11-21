"""Offline tests for lynx_agent_touch (no phone, no /dev/input)."""

import io
import json
from contextlib import redirect_stdout
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import lynx_agent_touch as touch  # noqa: E402
import lynx_noob_runtime as rt  # noqa: E402


def runtime_reply(fd=3, down=False, items=0, dropped=0):
    """The detail the real runtime handler produces, formatted as NRP/1 does."""
    fake = type("R", (), {})()
    queue = rt.RecordQueue()
    for i in range(items):
        queue.push({"x": i})
    queue.dropped = dropped
    fake.touch = type("T", (), {"fd": fd, "down": down, "events": queue})()
    value, detail = rt.Runtime.touch_status(fake, [], "")
    return f"NRP/1 7 OK value={value} detail={detail}"


class FakeRuntime:
    """A real AF_UNIX server that records what it receives."""

    def __init__(self, lines, hold=0.0):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "noobd.sock")
        self.server = socket.socket(socket.AF_UNIX)
        self.server.bind(self.path)
        self.server.listen(1)
        self.lines, self.received, self.hold = lines, [], hold
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def serve(self):
        conn, _ = self.server.accept()
        with conn, conn.makefile("rb") as stream:
            self.received.append(stream.readline().decode())
            for line in self.lines:
                conn.sendall(line.encode() + b"\n")
            if self.hold:
                threading.Event().wait(self.hold)  # connected but silent

    def close(self):
        self.server.close()
        self.dir.cleanup()


class TouchToolTest(unittest.TestCase):
    def call(self, lines, timeout=2.0):
        fake = FakeRuntime(lines)
        try:
            reply = touch.nrp(touch.COMMAND, fake.path, timeout)
            fake.thread.join(2)
            return reply, fake.received
        finally:
            fake.close()

    def test_sends_only_touch_status_and_parses_real_runtime_format(self):
        reply, received = self.call([runtime_reply(down=True, items=3, dropped=2)])
        self.assertEqual(received, ["NRP/1 7 CALL TOUCH_STATUS\n"])
        self.assertEqual(touch.parse(reply), {
            "ok": True, "panel_open": True, "finger_down": True, "queued": 3,
            "dropped": 2, "consumes_events": False})

    def test_panel_closed_is_reported(self):
        out = touch.parse(runtime_reply(fd=None))
        self.assertFalse(out["panel_open"])

    def test_event_lines_before_reply_are_skipped(self):
        reply, _ = self.call(["NRP/1 0 EVENT seq=1", runtime_reply()])
        self.assertEqual(touch.parse(reply)["queued"], 0)

    def test_never_sends_a_consuming_command(self):
        for command in ("CALL TOUCH_POLL", "CALL HAPTIC_SET 80 1", ""):
            with self.subTest(command=command), self.assertRaises(ValueError):
                touch.nrp(command, "/nonexistent")
        source = Path(touch.__file__).read_text()
        self.assertNotIn("TOUCH_POLL\"", source.replace("(381)", ""))

    def test_rejects_malformed_and_impossible_replies(self):
        for reply in ("NRP/1 7 ERR native failed", "NRP/1 7 OK value=1",
                      "NRP/1 7 OK value=1 detail=panel=touchpanel down=2 queued=0 dropped=0",
                      "NRP/1 7 OK value=1 detail=panel=touchpanel down=0 queued=9 dropped=0"):
            with self.subTest(reply=reply), self.assertRaises(RuntimeError):
                touch.parse(reply)

    def test_timeout_when_runtime_is_silent(self):
        fake = FakeRuntime([], hold=1.0)
        try:
            with self.assertRaises(TimeoutError):
                touch.nrp(touch.COMMAND, fake.path, timeout=0.2)
        finally:
            fake.close()

    def test_runtime_closing_without_reply_is_an_error(self):
        fake = FakeRuntime([])
        try:
            with self.assertRaisesRegex(RuntimeError, "incomplete"):
                touch.nrp(touch.COMMAND, fake.path, timeout=1.0)
        finally:
            fake.close()

    def test_main_rejects_arguments_and_reports_errors_as_json(self):
        with mock.patch("sys.stdin", io.StringIO('{"max": 3}')), redirect_stdout(io.StringIO()) as buf:
            self.assertEqual(touch.main(call=lambda c: runtime_reply()), 1)
        self.assertEqual(json.loads(buf.getvalue())["error"], "ValueError")
        with mock.patch("sys.stdin", io.StringIO("")), redirect_stdout(io.StringIO()) as buf:
            self.assertEqual(touch.main(call=lambda c: runtime_reply(items=1)), 0)
        self.assertEqual(json.loads(buf.getvalue())["queued"], 1)

        def missing(_):
            raise FileNotFoundError("/run/lynx/noobd.sock")
        with mock.patch("sys.stdin", io.StringIO("{}")), redirect_stdout(io.StringIO()) as buf:
            self.assertEqual(touch.main(call=missing), 1)
        self.assertFalse(json.loads(buf.getvalue())["ok"])


if __name__ == "__main__":
    unittest.main()
