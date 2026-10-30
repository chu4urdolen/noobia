"""Exercise signed Nexus TCP requests and root-local VM sharing offline."""

import multiprocessing
import os
from pathlib import Path
import re
import signal
import socket
from tempfile import TemporaryDirectory
import time
import unittest

from lynx_ble_auth import envelope
from lynx_noob_runtime import serve


KEY = bytes(range(32))


def line(stream):
    return stream.readline(4097)


class AuthTransportTest(unittest.TestCase):
    def test_unauthenticated_tcp_cannot_issue_but_local_vm_is_shared(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            key = root / "nexus.key"
            key.write_bytes(KEY)
            key.chmod(0o600)
            local_path = root / "nrp.sock"
            with socket.socket() as reserve:
                reserve.bind(("127.0.0.1", 0))
                port = reserve.getsockname()[1]
            process = multiprocessing.Process(
                target=serve, args=("127.0.0.1", port, "127.0.0.1",
                                    str(local_path), os.getuid(), str(key)))
            process.start()
            try:
                deadline = time.monotonic() + 3
                while not local_path.is_socket() and time.monotonic() < deadline:
                    if not process.is_alive():
                        self.fail("NRP server exited before opening local socket")
                    time.sleep(0.02)
                self.assertTrue(local_path.is_socket())
                with socket.create_connection(("127.0.0.1", port), timeout=2) as plain:
                    plain.settimeout(2)
                    self.assertRegex(plain.makefile("rb").readline(),
                                     rb"^AUTH/1 CHALLENGE [0-9a-f]{64}\n$")
                    plain.sendall(b"NRP/1 1 LOAD 00\n")
                    self.assertEqual(plain.recv(128), b"")
                with socket.create_connection(("127.0.0.1", port), timeout=2) as conn:
                    conn.settimeout(2)
                    with conn.makefile("rb") as stream:
                        challenge = line(stream)
                        match = re.fullmatch(rb"AUTH/1 CHALLENGE ([0-9a-f]{64})\n", challenge)
                        self.assertIsNotNone(match)
                        nonce = bytes.fromhex(match.group(1).decode())
                        signed = envelope(KEY, nonce, 1, b"NRP/1 2 LOAD 00\n", 4096)
                        conn.sendall(signed)
                        self.assertEqual(line(stream), b"NRP/1 2 OK loaded=1\n")
                        conn.sendall(envelope(KEY, nonce, 2, b"NRP/1 3 STATUS\n", 4096))
                        self.assertIn(b"state=READY", line(stream))
                with socket.socket(socket.AF_UNIX) as local:
                    local.settimeout(2)
                    local.connect(str(local_path))
                    local.sendall(b"NRP/1 4 STATUS\n")
                    self.assertIn(b"state=READY", local.recv(256))
            finally:
                if process.is_alive():
                    os.kill(process.pid, signal.SIGTERM)
                process.join(3)
                if process.is_alive():
                    process.kill()
                    process.join(2)


if __name__ == "__main__":
    unittest.main()
