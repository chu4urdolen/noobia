#!/usr/bin/env python3
"""Offline checks for the bounded Lynx BLE diagnostic GATT endpoint."""

import asyncio
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch
from pathlib import Path

from dbus_next import DBusError, Variant
from dbus_next.service import ServiceInterface

from lynx_ble_auth import Authenticator, envelope, fragments
from lynx_ble_gatt_probe import (ChallengeCharacteristic, ObjectManager,
                                  RequestCharacteristic, ResponseCharacteristic,
                                  forward_nrp)


DEVICE = "/org/bluez/hci0/dev_00_11_22_33_44_55"
KEY = bytes(range(32))
CHALLENGE = bytes(range(32, 64))


class ProbeTests(unittest.TestCase):
    def test_object_tree_and_signatures(self):
        managed = ObjectManager.GetManagedObjects.__wrapped__(ObjectManager())
        self.assertEqual(len(managed), 4)
        for path, interfaces in managed.items():
            self.assertTrue(path.startswith("/org/noobia/lynx/service0"))
            for props in interfaces.values():
                self.assertTrue(all(isinstance(v, Variant) for v in props.values()))
        reply = ResponseCharacteristic()
        request = RequestCharacteristic(reply, Authenticator(KEY, CHALLENGE))
        self.assertEqual([x.name for x in ServiceInterface.introspect(request).methods],
                         ["WriteValue"])
        self.assertEqual([x.name for x in ServiceInterface.introspect(reply).methods],
                         ["ReadValue"])

    def test_unauthenticated_write_never_reaches_socket(self):
        request = RequestCharacteristic(ResponseCharacteristic(),
                                        Authenticator(KEY, CHALLENGE))
        write = RequestCharacteristic.WriteValue.__wrapped__
        for frame in (b"NRP/1 1 PING\n", b"NRP/1 1 CALL HAPTIC_SET 80 1\n"):
            with self.subTest(frame=frame), self.assertRaises(DBusError):
                asyncio.run(write(request, frame, {"device": Variant("o", DEVICE)}))

    def test_signed_vm_request_is_forwarded_and_reply_is_peer_scoped(self):
        reply = ResponseCharacteristic()
        request = RequestCharacteristic(reply, Authenticator(KEY, CHALLENGE))
        frame = envelope(KEY, CHALLENGE, 1, b"NRP/1 12 LOAD 00\n")
        with patch("lynx_ble_gatt_probe.forward_nrp",
                   return_value=b"NRP/1 12 OK loaded=1\n") as forward:
            for chunk in fragments(frame):
                asyncio.run(RequestCharacteristic.WriteValue.__wrapped__(
                    request, chunk, {"device": Variant("o", DEVICE)}))
        forward.assert_called_once_with(b"NRP/1 12 LOAD 00\n")
        self.assertEqual(bytes(ResponseCharacteristic.ReadValue.__wrapped__(
            reply, {"device": Variant("o", DEVICE)})), b"NRP/1 12 OK loaded=1\n")
        with self.assertRaises(DBusError):
            ResponseCharacteristic.ReadValue.__wrapped__(
                reply, {"device": Variant("o", "/org/bluez/hci0/dev_OTHER")})

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
                self.assertEqual(forward_nrp(b"NRP/1 42 PING\n", path),
                                 b"NRP/1 42 OK PONG\n")
            finally:
                worker.join(2)
                server.close()

    def test_response_offsets(self):
        response = ResponseCharacteristic()
        response.set_reply(DEVICE, b"NRP/1 42 OK PONG\n")
        read = ResponseCharacteristic.ReadValue.__wrapped__
        options = {"device": Variant("o", DEVICE)}
        self.assertEqual(bytes(read(response, options)), b"NRP/1 42 OK PONG\n")
        options["offset"] = Variant("q", 8)
        self.assertEqual(bytes(read(response, options)), b" OK PONG\n")
        with self.assertRaises(DBusError):
            read(response, {"device": Variant("o", "/other")})

    def test_challenge_and_authenticated_forwarding(self):
        auth = Authenticator(KEY, CHALLENGE)
        challenge = ChallengeCharacteristic(auth)
        self.assertEqual(bytes(ChallengeCharacteristic.ReadValue.__wrapped__(challenge, {})),
                         auth.challenge_line())
        signed = envelope(KEY, CHALLENGE, 1, b"NRP/1 42 PING\n")
        self.assertEqual(auth.accept(signed), b"NRP/1 42 PING\n")


if __name__ == "__main__":
    unittest.main()
