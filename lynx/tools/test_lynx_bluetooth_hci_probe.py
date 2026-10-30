"""Protocol checks for the stock H4 transport parser, without radio access."""

import socket
import threading
import unittest

from lynx_bluetooth_hci_probe import HCI, advertising_parameters, event_frames


class HCITest(unittest.TestCase):
    def test_le_advertising_parameters_have_full_hci_length(self):
        params = advertising_parameters()
        self.assertEqual(len(params), 15)
        self.assertEqual(params[6], 0)  # direct address type
        self.assertEqual(params[13:], b"\x07\x00")

    def test_fragmented_event_and_command_opcode(self):
        left, right = socket.socketpair()
        received = []

        def device():
            received.append(right.recv(4))
            right.sendall(b"\x04\xff\x00\x04\x0e")
            right.sendall(b"\x04\x01\x03\x0c\x00")

        worker = threading.Thread(target=device)
        worker.start()
        try:
            self.assertEqual(HCI(left.fileno()).command(0x0c03, timeout=1), b"")
            self.assertEqual(received, [b"\x01\x03\x0c\x00"])
        finally:
            worker.join(timeout=1)
            left.close()
            right.close()

    def test_retains_incomplete_tail(self):
        buffer = bytearray(b"\x04\x0e\x04\x01")
        self.assertEqual(event_frames(buffer), [])
        buffer.extend(b"\x09\x10\x00")
        self.assertEqual(event_frames(buffer), [b"\x04\x0e\x04\x01\x09\x10\x00"])
        self.assertEqual(buffer, bytearray())

    def test_acl_payload_does_not_create_false_event(self):
        buffer = bytearray(b"\x02\x01\x20\x04\x00\x04\x3e\x01\x00"
                           b"\x04\x3e\x04\x01\x00\x01\x00")
        self.assertEqual(event_frames(buffer), [b"\x04\x3e\x04\x01\x00\x01\x00"])
        self.assertEqual(buffer, bytearray())


if __name__ == "__main__":
    unittest.main()
