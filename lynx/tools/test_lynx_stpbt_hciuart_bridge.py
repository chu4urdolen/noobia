"""Check H4 framing and that bridge diagnostics omit packet payloads."""

import unittest

from lynx_stpbt_hciuart_bridge import correct_sync_train_capability, record_h4


class H4TraceTest(unittest.TestCase):
    def test_split_reset_command_and_completion(self):
        report = {"host_commands": [], "controller_events": []}
        host = bytearray()
        controller = bytearray()
        record_h4(bytes.fromhex("01030c"), host, "host", report)
        self.assertEqual(report["host_commands"], [])
        record_h4(bytes.fromhex("00"), host, "host", report)
        record_h4(bytes.fromhex("040e0401030c00"), controller, "controller", report)
        self.assertEqual(report["host_commands"], ["0c03"])
        self.assertEqual(report["controller_events"],
                         [{"event": "0e", "opcode": "0c03", "status": 0}])

    def test_acl_payload_is_not_recorded(self):
        report = {"host_commands": [], "controller_events": []}
        data = bytes.fromhex("0201000300deadbe")
        record_h4(data, bytearray(), "controller", report)
        self.assertEqual(report["controller_events"], [])

    def test_only_page_two_sync_train_bit_is_corrected(self):
        # H4 event, command complete, Read Local Extended Features, page 2.
        original = bytes.fromhex("040e0e0104100002020500000000000000")
        report = {"sync_train_capability_corrected": 0}
        pending = bytearray()
        self.assertEqual(correct_sync_train_capability(original[:7], pending, report), b"")
        changed = correct_sync_train_capability(original[7:], pending, report)
        self.assertEqual(changed, original[:9] + b"\x01" + original[10:])
        self.assertEqual(report["sync_train_capability_corrected"], 1)
        self.assertEqual(pending, b"")
        page_one = bytearray(original)
        page_one[7] = 1
        self.assertEqual(correct_sync_train_capability(page_one, pending, report), page_one)
        self.assertEqual(report["sync_train_capability_corrected"], 1)


if __name__ == "__main__":
    unittest.main()
