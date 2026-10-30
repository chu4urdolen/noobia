#!/usr/bin/env python3
"""Offline checks for the bounded Lynx BLE diagnostic GATT endpoint."""

import socket
import tempfile
import threading
import unittest
from pathlib import Path

from dbus_next import Variant
from dbus_next.service import ServiceInterface

from lynx_ble_gatt_probe import (ObjectManager, RequestCharacteristic,
                                  ResponseCharacteristic, forward_read_only)


class ProbeTests(unittest.TestCase):
    def test_object_tree_and_signatures(self):
        managed = ObjectManager.GetManagedObjects.__wrapped__(ObjectManager())
        self.assertEqual(len(managed), 3)
        for path, interfaces in managed.items():
            self.assertTrue(path.startswith("/org/noobia/lynx/service0"))
            for props in interfaces.values():
                self.assertTrue(all(isinstance(v, Variant) for v in props.values()))
        reply = ResponseCharacteristic()
        request = RequestCharacteristic(reply)
        self.assertEqual([x.name for x in ServiceInterface.introspect(request).methods],
                         ["WriteValue"])
        self.assertEqual([x.name for x in ServiceInterface.introspect(reply).methods],
                         ["ReadValue"])

    def test_rejects_all_controls_without_socket_access(self):
        for request in (b"NRP/1 1 CALL HAPTIC_SET 80 1\n", b"NRP/1 1 LOAD 01\n",
                        b"NRP/1 1 PING\nNRP/1 2 INFO\n", b"NRP/1 1 PING",
                        b"NRP/1 1 INFO extra\n", b"NRP/1 1 PING\x00\n"):
            with self.subTest(request=request), self.assertRaises(ValueError):
                forward_read_only(request, "/does-not-exist")

    def test_forwarding_preserves_request_id(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "noobd.sock")
            server = socket.socket(socket.AF_UNIX)
            server.bind(path)
            server.listen(1)

            def answer():
                conn, _ = server.accept()
                with conn:
                    self.assertEqual(conn.recv(128), b"NRP/1 42 PING\n")
                    conn.sendall(b"NRP/1 42 OK PONG\n")

            worker = threading.Thread(target=answer)
            worker.start()
            try:
                self.assertEqual(forward_read_only(b"NRP/1 42 PING\n", path),
                                 b"NRP/1 42 OK PONG\n")
            finally:
                worker.join(2)
                server.close()

    def test_response_offsets(self):
        response = ResponseCharacteristic()
        response.value = b"NRP/1 42 OK PONG\n"
        read = ResponseCharacteristic.ReadValue.__wrapped__
        self.assertEqual(bytes(read(response, {"offset": Variant("q", 0)})),
                         response.value)
        self.assertEqual(bytes(read(response, {"offset": Variant("q", 8)})),
                         response.value[8:])


if __name__ == "__main__":
    unittest.main()
