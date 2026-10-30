"""Check that the optional local transport shares Lynx's Wi-Fi NRP runtime."""

import multiprocessing
import os
from pathlib import Path
import signal
import socket
from tempfile import TemporaryDirectory
import time
import unittest

from lynx_noob_runtime import serve


def request(sock, text):
    sock.sendall((text + "\n").encode())
    reply = bytearray()
    while b"\n" not in reply:
        reply.extend(sock.recv(4096))
    return reply.split(b"\n", 1)[0].decode()


class LocalSocketTest(unittest.TestCase):
    def test_local_and_tcp_share_one_vm(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "nrp.sock"
            with socket.socket() as reserve:
                reserve.bind(("127.0.0.1", 0))
                port = reserve.getsockname()[1]
            process = multiprocessing.Process(
                target=serve, args=("127.0.0.1", port, "127.0.0.1",
                                    str(path), os.getuid()))
            process.start()
            try:
                deadline = time.monotonic() + 3
                while not path.is_socket() and time.monotonic() < deadline:
                    if not process.is_alive():
                        self.fail("NRP service exited before opening local socket")
                    time.sleep(0.02)
                self.assertTrue(path.is_socket())
                with socket.socket(socket.AF_UNIX) as local:
                    local.settimeout(2)
                    local.connect(str(path))
                    self.assertEqual(request(local, "NRP/1 1 PING"), "NRP/1 1 OK PONG")
                    loaded = request(local, "NRP/1 2 LOAD 01002a00000021e803100600")
                    self.assertIn("loaded=12", loaded)
                with socket.create_connection(("127.0.0.1", port), timeout=2) as tcp:
                    tcp.settimeout(2)
                    status = request(tcp, "NRP/1 3 STATUS")
                    self.assertIn("state=READY", status)
                    self.assertIn("bytes=12", status)
            finally:
                if process.is_alive():
                    os.kill(process.pid, signal.SIGTERM)
                process.join(timeout=3)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=2)
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
