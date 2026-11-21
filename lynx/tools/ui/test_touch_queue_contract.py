"""Offline contract tests for Lynx's touch event queue (TOUCH_STATUS / TOUCH_POLL).

They pin the facts in lynx/linux-port/docs/LYNX-TOUCH-EVENTS-DESIGN-20261121.md
using the real RecordQueue and Runtime handlers. They never open
/dev/input or contact Lynx.
"""

from pathlib import Path
import sys
import unittest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import lynx_noob_runtime as rt  # noqa: E402


class TouchQueueContract(unittest.TestCase):
    def test_capacity_eight_drops_oldest_and_counts(self):
        queue = rt.RecordQueue()
        for i in range(10):
            queue.push({"x": i})
        self.assertEqual(len(queue.items), 8)
        self.assertEqual(queue.dropped, 2)
        self.assertEqual(queue.pop()[0], 2)  # 0 and 1 were dropped

    def test_poll_consumes_and_empty_is_safe(self):
        queue = rt.RecordQueue()
        queue.push({"down": 1})
        value, detail = queue.pop(True)
        self.assertEqual(value, 1)
        self.assertIn("remaining=0", detail)
        self.assertEqual(queue.pop(True), (0, "event=0 queued=0"))  # consumed
        with self.assertRaises(rt.NativeError):
            queue.pop()

    def test_status_reads_without_consuming(self):
        fake = type("R", (), {})()
        fake.touch = type("T", (), {"fd": 3, "down": False, "events": rt.RecordQueue()})()
        fake.touch.events.push({"x": 5})
        value, detail = rt.Runtime.touch_status(fake, [], "")
        self.assertEqual(value, 1)
        self.assertIn("queued=1", detail)
        self.assertEqual(len(fake.touch.events.items), 1)  # still there
        self.assertEqual(rt.Runtime.touch_poll(fake, [], "")[0], 5)
        self.assertEqual(len(fake.touch.events.items), 0)  # poll consumed it

    def test_single_shared_device_and_queue(self):
        self.assertEqual(rt.TOUCH_DEVICE, "/dev/input/event0")
        source = (TOOLS / "lynx_noob_runtime.py").read_text()
        self.assertNotIn("EVIOCGRAB", source)  # no exclusive grab
        self.assertEqual(source.count("self.touch.events.pop("), 1)  # only TOUCH_POLL pops


if __name__ == "__main__":
    unittest.main()
