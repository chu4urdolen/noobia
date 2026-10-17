"""Check that the exact V26b init tail survives a refused OpenRC handoff."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / 'linux-port'
sys.path.insert(0, str(PORT))
from image_formats import read_boot_v4, read_newc  # noqa: E402
from ramdisk_codec import decompress  # noqa: E402


def main():
    os.umask(0o077)
    folder = PORT / 'artifacts/selfboot-alpine-v26b-offline'
    image = (folder / 'nord3-selfboot-alpine-untested.img').read_bytes()
    manifest = json.loads((folder / 'build-result.json').read_text())
    if hashlib.sha256(image).hexdigest() != manifest['image_sha256']:
        raise ValueError('V26b image changed')
    init = read_newc(decompress(read_boot_v4(image)['ramdisk']))['init']['data']
    tail_start = b"log 'LOCAL_SELFBOOT_WIFI_SSH_HEALTH_ACTIVE; ATTEMPTING_ALPINE_PID1'\n"
    if init.count(tail_start) != 1:
        raise ValueError('Expected V26b handoff site missing')
    tail = init[init.index(tail_start):].decode()
    with tempfile.TemporaryDirectory(prefix='lynx-rescue-', dir=PORT / 'artifacts') as temp:
        base = Path(temp)
        stub = base / 'openrc-local-handoff.sh'
        stub.write_text('lynx_openrc_local_handoff() { set -eu; return 1; }\n')
        old = '/etc/lynx/openrc-local-handoff.sh'
        if tail.count(old) != 1:
            raise ValueError('Expected local handoff source differs')
        tail = tail.replace(old, str(stub))
        runner = base / 'runner.sh'
        runner.write_text(
            '#!/bin/sh\nset -eu\n'
            'log() { printf "LOG %s\\n" "$*"; }\n'
            'stop() { echo BUSYBOX_RESCUE_STILL_PID1; exit 0; }\n' + tail)
        result = subprocess.run(['sh', str(runner)], capture_output=True,
                                text=True, timeout=5)
        if result.returncode or result.stdout.count('BUSYBOX_RESCUE_STILL_PID1') != 1 or \
                'LOCAL_OPENRC_HANDOFF_REFUSED' not in result.stdout:
            raise AssertionError('Refused handoff did not keep rescue PID 1: ' +
                                 result.stdout + result.stderr)
    out = PORT / 'artifacts' / ('openrc-local-rescue-check-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    report = {'state': 'v26b-refusal-keeps-busybox-pid1',
              'image_sha256': manifest['image_sha256'],
              'init_sha256': hashlib.sha256(init).hexdigest(),
              'test_exit_code': result.returncode,
              'phone_contacted': False, 'flash_performed': False,
              'limits': 'Host shell fixture; actual handset exec failure remains untested.'}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(out / 'result.json')}))


if __name__ == '__main__':
    main()
