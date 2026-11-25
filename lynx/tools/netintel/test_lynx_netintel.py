"""Offline tests for lynx-netintel (LNX-12/13/14/15/18/48/49/50)."""
import socket
import struct
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lynx_netintel as n  # noqa: E402


def _rr(name_bytes, rtype, rdata):
    return name_bytes + struct.pack(">HHIH", rtype, 1, 120, len(rdata)) + rdata


class DnsTest(unittest.TestCase):
    def test_parse_ptr_with_compression_a_and_srv(self):
        q = n._qname("_services._dns-sd._udp.local")
        head = struct.pack(">6H", 0, 0x8400, 1, 1, 0, 2)
        body = q + struct.pack(">HH", 12, 1)
        ptr = _rr(b"\xc0\x0c", 12, n._qname("_hue._tcp.local"))
        a = _rr(n._qname("bridge.local"), 1, socket.inet_aton("192.168.100.3"))
        srv = _rr(n._qname("x._hue._tcp.local"), 33, struct.pack(">3H", 0, 0, 443) + n._qname("bridge.local"))
        out = n.parse_dns(head + body + ptr + a + srv)
        self.assertEqual(out[0], ("_services._dns-sd._udp.local", 12, "_hue._tcp.local"))
        self.assertEqual(out[1], ("bridge.local", 1, "192.168.100.3"))
        self.assertEqual(out[2][2], "bridge.local:443")

    def test_garbage_never_raises(self):
        for data in (b"", b"\x00" * 11, b"\xff" * 40):
            n.parse_dns(data)

    def test_clean_strips_control_and_clips(self):
        self.assertEqual(n.clean("\x1b[31mhi\x07  there" + "x" * 100, 10), "[31mhi the")


class LocalTest(unittest.TestCase):
    def test_conn_table_and_snmp_read_this_machine(self):
        self.assertIn("by_service", n.conn_table())
        self.assertIn("Tcp", n.snmp())

    def test_nrp_greeting_and_tcp_open(self):
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]

        def serve():
            c, _ = srv.accept()
            c.sendall(b"NRP/1 0 CHALLENGE abc\n")
            c.close()
        threading.Thread(target=serve, daemon=True).start()
        self.assertTrue(n.nrp_greeting("127.0.0.1", port).startswith("NRP/1"))
        srv.close()
        self.assertFalse(n.tcp_open("127.0.0.1", port, 0.3))

    def test_policy_gate_fails_closed_without_policy(self):
        old = n.POLICY
        n.POLICY = [Path("/nonexistent")]
        try:
            self.assertEqual(n.authorized("ble-scan")[0], False)
        finally:
            n.POLICY = old


if __name__ == "__main__":
    unittest.main()
