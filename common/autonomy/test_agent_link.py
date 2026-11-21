"""Tests for the Aigel <-> agent interface (agent_link.py)."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import agent_link as al  # noqa: E402

NOW = datetime(2026, 11, 21, 14, 0, tzinfo=timezone.utc)


def msg(**changes):
    m = al.make_message("lynx", "ranker", "observation", "A cat appeared in front of you",
                        ["NOOBIA P1 camera object.seen label=cat conf=0.91"], "cat-seen", NOW)
    m.update(changes)
    return m


class Recorder(al.Adapter):
    def __init__(self, *a, fail=False, **k):
        self.sent, self.fail = [], fail
        super().__init__(*a, **k)

    def _send(self, message):
        if self.fail:
            raise ConnectionError("agent unreachable")
        self.sent.append(message["id"])


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class SchemaTest(unittest.TestCase):
    def test_make_message_is_valid_and_complete(self):
        m = msg()
        self.assertEqual(set(m), al.FIELDS)
        self.assertEqual(m["time"], "2026-11-21T14:00:00Z")
        self.assertRegex(m["id"], r"^[0-9a-f]{32}$")
        self.assertEqual(json.loads(json.dumps(m)), m)

    def test_rejects_every_kind_of_bad_message(self):
        cases = {
            "extra field": dict(msg(), extra=1),
            "version": msg(v=2),
            "id": msg(id="not-hex"),
            "host": msg(host="Lynx Phone"),
            "time": msg(time="21/11/2026"),
            "source": msg(source="gwyn"),
            "kind": msg(kind="command"),
            "empty text": msg(text="   "),
            "long text": msg(text="x" * 501),
            "multi-line": msg(text="hello\nrm -rf /"),
            "evidence count": msg(evidence=["x"] * 11),
            "evidence size": msg(evidence=["x" * 513]),
            "aigel with pattern": msg(source="aigel"),
        }
        for label, m in cases.items():
            with self.subTest(label), self.assertRaises(al.MessageError):
                al.validate(m)
        missing = msg()
        del missing["kind"]
        with self.assertRaises(al.MessageError):
            al.validate(missing)

    def test_total_size_bounded(self):
        m = msg(text="ж" * 500, evidence=["ж" * 170] * 10)
        with self.assertRaisesRegex(al.MessageError, "exceeds"):
            al.validate(m)

    def test_aigel_messages_have_no_pattern(self):
        m = al.make_message("lynx", "aigel", "alert", "The Noobia Wi-Fi is down", now=NOW)
        self.assertIsNone(m["pattern_id"])


class AdapterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.switch = self.dir / "autonomy.disable"
        self.logs = []
        self.clock = Clock()

    def tearDown(self):
        self.tmp.cleanup()

    def adapter(self, **k):
        return Recorder(self.dir / "state", kill_switch=self.switch, log=self.logs.append,
                        clock=self.clock, **k)

    def test_delivers_and_logs(self):
        a, m = self.adapter(), msg()
        r = a.deliver(m)
        self.assertEqual(r["status"], "delivered")
        self.assertEqual(a.sent, [m["id"]])
        self.assertIn(f"status=delivered id={m['id']}", self.logs[-1])

    def test_idempotent_even_across_restarts(self):
        m = msg()
        self.adapter().deliver(m)
        again = self.adapter()                 # a new process, same state dir
        self.assertEqual(again.deliver(m)["status"], "duplicate")
        self.assertEqual(again.sent, [])

    def test_kill_switch(self):
        self.switch.touch()
        a = self.adapter()
        self.assertEqual(a.deliver(msg())["status"], "disabled")
        self.assertEqual(a.sent, [])
        self.switch.unlink()
        self.assertEqual(a.deliver(msg())["status"], "delivered")

    def test_rate_limit_sliding_window(self):
        a = self.adapter(max_per_minute=2)
        statuses = [a.deliver(msg())["status"] for _ in range(3)]
        self.assertEqual(statuses, ["delivered", "delivered", "rate_limited"])
        self.clock.t += 60
        self.assertEqual(a.deliver(msg())["status"], "delivered")

    def test_failed_send_is_retryable(self):
        m = msg()
        failing = self.adapter(fail=True)
        r = failing.deliver(m)
        self.assertEqual(r["status"], "failed")
        self.assertIn("ConnectionError", r["detail"])
        failing.fail = False                                       # same running adapter
        self.assertEqual(failing.deliver(m)["status"], "delivered")
        self.assertEqual(failing.sent, [m["id"]])

    def test_rejected_messages_are_never_sent(self):
        a = self.adapter()
        self.assertEqual(a.deliver(msg(kind="command"))["status"], "rejected")
        self.assertEqual(a.deliver("not a dict")["status"], "rejected")
        self.assertEqual(a.sent, [])

    def test_remembered_ids_bounded_and_corrupt_state_tolerated(self):
        a = self.adapter(remember=5, max_per_minute=100)
        for _ in range(8):
            a.deliver(msg())
        stored = json.loads((self.dir / "state" / "delivered_ids.json").read_text())
        self.assertEqual(len(stored), 5)
        (self.dir / "state" / "delivered_ids.json").write_text("{corrupt")
        self.assertEqual(self.adapter().deliver(msg())["status"], "delivered")

    def test_base_class_requires_send(self):
        base = al.Adapter(self.dir / "s2", kill_switch=self.switch, log=self.logs.append)
        self.assertEqual(base.deliver(msg())["status"], "failed")


if __name__ == "__main__":
    unittest.main()
