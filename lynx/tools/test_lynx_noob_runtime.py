#!/usr/bin/env python3
"""Host checks for Lynx's NRP/1, common VM and sequence behavior."""

import time
import unittest

from lynx_noob_runtime import Runtime


class RuntimeTest(unittest.TestCase):
    def setUp(self):
        self.runtime = Runtime()

    def test_nrp_frame_and_common_vm(self):
        r = self.runtime
        self.assertEqual(r.dispatch("NRP/1 9 PING"), "NRP/1 9 OK PONG")
        self.assertIn("protocol=1 vm=1", r.dispatch("NRP/1 3 INFO"))
        self.assertIn("3:SEQUENCE_SET", r.dispatch("NRP/1 4 CAPS"))
        self.assertIn("loaded=12", r.dispatch("NRP/1 5 LOAD 01002a00000021e803100600"))
        self.assertIn("OK started", r.dispatch("NRP/1 6 RUN"))
        r.tick()
        self.assertIn("state=WAITING", r.dispatch("NRP/1 7 STATUS"))
        self.assertIn("state=STOPPED", r.dispatch("NRP/1 8 STOP"))

    def test_mixed_sequence_uses_iris_bit_order_and_eight_record_queue(self):
        r = self.runtime
        calls = []
        r.registry.by_id[300] = ("HAPTIC_SET", lambda args, text:
                                  (calls.append((args[:], text)) or (args[-1], "")))
        self.assertIn("bits=10", r.dispatch(
            'NRP/1 1 CALL_MIXED SEQUENCE_SET 0 10 300 2 2 1 80 ""'))
        self.assertEqual(r.sequence.tracks[0]["fixed"], [80])
        self.assertIn("OK value=1", r.dispatch("NRP/1 2 CALL SEQUENCE_START"))
        r.sequence.tick()
        time.sleep(0.012)
        r.sequence.tick()
        self.assertEqual(calls, [([80, 1], ""), ([80, 0], "")])
        self.assertIn("value=2", r.dispatch("NRP/1 3 CALL SEQUENCE_QUEUE_SIZE 0"))
        self.assertIn("value=1", r.dispatch("NRP/1 4 CALL SEQUENCE_POP 0"))
        self.assertIn("value=0", r.dispatch("NRP/1 5 CALL SEQUENCE_BUSY 0"))
        self.assertEqual(r.sequence.events.pop(), "SEQUENCE_COMPLETE")

    def test_vm_haptic_program_is_wire_compatible(self):
        from pathlib import Path
        r = self.runtime
        r.registry.by_id[300] = ("HAPTIC_SET", lambda args, text: (args[-1], ""))
        program = Path(__file__).resolve().parent.parent / "programs/haptic_two_pulses.hex"
        self.assertIn("loaded=61", r.dispatch("NRP/1 1 LOAD " + program.read_text().strip()))
        self.assertIn("OK started", r.dispatch("NRP/1 2 RUN"))
        r.vm.tick()
        self.assertEqual(r.vm.state, "HALTED")
        self.assertEqual(r.sequence.tracks[0]["bits"], [1, 0, 1, 0])

    def test_thread_queue_and_stop(self):
        r = self.runtime
        seen = []
        r.cycle.step = lambda: (seen.append(1), r.cycle.events.push({"value": 1}))
        self.assertIn("running=1", r.dispatch("NRP/1 1 CALL IMAGE_CYCLE_START 100"))
        r.cycle.tick()
        self.assertEqual(len(seen), 1)
        self.assertIn("value=1", r.dispatch("NRP/1 2 CALL IMAGE_CYCLE_POLL"))
        self.assertIn("event=0", r.dispatch("NRP/1 3 CALL IMAGE_CYCLE_POLL"))
        self.assertIn("running=0", r.dispatch("NRP/1 4 CALL IMAGE_CYCLE_STOP"))


if __name__ == "__main__":
    unittest.main()
