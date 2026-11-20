"""Haptic pulse always sends STOP and verifies the inactive state."""

import unittest

from lynx_agent_haptic import COMMANDS, pulse


class HapticAgentTest(unittest.TestCase):
    def test_pulse_stops_and_checks_same_boot(self):
        calls = []
        status = iter((0, 0))
        def call(command):
            calls.append(command)
            return next(status) if command == COMMANDS["status"] else 1
        result = pulse(call, lambda: {"boot_id": "boot"}, lambda _: None)
        self.assertEqual(calls, [COMMANDS["status"], COMMANDS["pulse"],
                                 COMMANDS["stop"], COMMANDS["status"]])
        self.assertTrue(result["off_verified"])

    def test_failure_after_set_still_stops(self):
        calls = []
        def call(command):
            calls.append(command)
            if command == COMMANDS["status"]:
                return 0
            if command == COMMANDS["pulse"]:
                return 1
            return 0
        with self.assertRaises(RuntimeError):
            pulse(call, lambda: {"boot_id": "boot"},
                  lambda _: (_ for _ in ()).throw(RuntimeError("interrupted")))
        self.assertEqual(calls[-1], COMMANDS["stop"])


if __name__ == "__main__":
    unittest.main()
