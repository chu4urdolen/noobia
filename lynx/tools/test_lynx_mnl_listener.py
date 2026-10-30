"""Safety check for the exact short stock GNSS control packets."""

import struct
import unittest

from lynx_mnl_listener import HAL_SOCKET, MNL_SOCKET, START, STOP


class MNLPacketTest(unittest.TestCase):
    def test_stock_start_stop_wire_format(self):
        self.assertEqual(START, bytes.fromhex("01000000660000003333b33f"))
        self.assertEqual(STOP, struct.pack("<II", 1, 103))
        self.assertEqual(len(HAL_SOCKET), 108)
        self.assertEqual(len(MNL_SOCKET), 108)
        self.assertNotEqual(HAL_SOCKET, MNL_SOCKET)


if __name__ == "__main__":
    unittest.main()
