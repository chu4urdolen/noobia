#!/usr/bin/env python3
import unittest
from common.autonomy import trigger, sense


class TestTriggerSumPriority(unittest.TestCase):
    def L(self, p, s="test", e="ev", text=""):
        return sense.format_line(p, s, e, text=text)

    def test_p20_triggers_immediately(self):
        c = trigger.Chunker(priority_mode="sum", priority_threshold=20)
        c.feed(self.L(0, text="sample"), 0.0)
        closed = c.feed(self.L(20, text="urgent"), 1.0)
        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0]["reason"], "priority")
        self.assertEqual(len(closed[0]["lines"]), 2)

    def test_multiple_p4_events_trigger_at_sum_20(self):
        c = trigger.Chunker(priority_mode="sum", priority_threshold=20)
        for i in range(4):
            res = c.feed(self.L(4, e=f"tap{i}"), float(i))
            self.assertEqual(res, [])
        # 5th event brings sum to 20
        res = c.feed(self.L(4, e="tap4"), 4.0)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["reason"], "priority")
        self.assertEqual(len(res[0]["lines"]), 5)

    def test_busy_accumulates_and_flushes_when_unbusy(self):
        busy_flag = True
        c = trigger.Chunker(priority_mode="sum", priority_threshold=20, is_busy=lambda: busy_flag)
        # Feed P20 while busy: should not close early
        res = c.feed(self.L(20, text="urgent"), 1.0)
        self.assertEqual(res, [])
        # Free busy flag and tick
        busy_flag = False
        closed = c.tick(2.0)
        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0]["reason"], "priority")


if __name__ == "__main__":
    unittest.main()
