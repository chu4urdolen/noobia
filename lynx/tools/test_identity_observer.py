"""Exercise a verified beacon without opening a socket or contacting Lynx."""
import contextlib
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import lynx_identity_observer as observer
from lynx_wifi_v19_contact import BB_SHA, BUILD, KERNEL, PROOF


class BeaconSocket:
    def __init__(self, *args, **kwargs):
        self.received = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def bind(self, address):
        assert address == (BUILD['collector_ip'], 5514)

    def settimeout(self, timeout):
        assert timeout == 0.5

    def recvfrom(self, size):
        assert size == 4096 and not self.received
        self.received = True
        return ('LYNX_HELLO ' + BUILD['session_token']).encode(), ('192.168.100.9', 5514)


def main():
    proof = ('LYNX_NATIVE_SSH_PROOF\n' + KERNEL + '\n/bin/busybox\n' +
             BUILD['init_sha256'] + '  /init\n' + BB_SHA + '  /bin/busybox\n' +
             BUILD['session_token'] + '\nuid=0(root)\n').encode()
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        assert command[-1] == PROOF
        assert '-o' in command and 'StrictHostKeyChecking=yes' in command
        assert kwargs['timeout'] == 15
        return subprocess.CompletedProcess(command, 0, proof, b'')

    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent.parent / 'linux-port/artifacts') as tmp:
        root = Path(tmp)
        (root / 'logs').mkdir()
        with patch.object(observer, 'ROOT', root), patch.object(observer.socket, 'socket', BeaconSocket), \
             patch.object(observer.subprocess, 'run', fake_run), \
             patch.object(sys, 'argv', ['lynx_identity_observer.py', '--listen', '--seconds', '1']), \
             contextlib.redirect_stdout(io.StringIO()):
            observer.main()
        results = list((root / 'logs').glob('identity-observer-*/result.json'))
        assert len(results) == 1
        report = json.loads(results[0].read_text())
        assert report['state'] == 'identity-verified'
        assert report['native_identity_verified'] and len(calls) == 1
        assert not report['phone_write_issued'] and not report['power_command_issued']
        assert not report['flash_performed']
    print('Passive observer: pinned proof accepted; one read-only SSH command; no phone action')


if __name__ == '__main__':
    main()
