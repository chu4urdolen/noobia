"""Exercise the exact V27a packaged Wi-Fi supervisor with fake devices."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / 'linux-port'
BUILD = PORT / 'artifacts/minimal-local-ssh-v27a-offline'
sys.path.insert(0, str(PORT))
from image_formats import read_boot_v4, read_newc
from ramdisk_codec import decompress


def packaged_script():
    manifest = json.loads((BUILD / 'build-result.json').read_text())
    image = (BUILD / 'nord3-minimal-local-ssh-untested.img').read_bytes()
    if hashlib.sha256(image).hexdigest() != manifest['image_sha256']:
        raise ValueError('V27a image differs from manifest')
    recipe = json.loads((PORT / 'known-good-v19/recipe.json').read_text())
    primary = read_newc(decompress(read_boot_v4(image)['ramdisk']))
    offset = recipe['payload_offset']
    length = int(primary['etc/lynx/payload-bytes']['data'])
    payload = image[offset:offset + length]
    if hashlib.sha256(payload).hexdigest() != manifest['payload_sha256']:
        raise ValueError('V27a payload differs from manifest')
    supplement = read_newc(gzip.decompress(payload))
    return supplement['etc/lynx/wifi-runtime.sh']['data'].decode()


def scenario(parent, script, success):
    base = parent / ('success' if success else 'failure')
    run = base / 'run/lynx'
    config = base / 'etc/lynx'
    net = base / 'sys/class/net'
    run.mkdir(parents=True)
    config.mkdir(parents=True)
    (net / 'wlan0').mkdir(parents=True)
    (config / 'host-ip').write_text('192.168.100.106\n')
    (config / 'session-token').write_text('fixture-token\n')
    for original, replacement in (
        ('/run/lynx', str(run)),
        ('/etc/lynx', str(config)),
        ('/sys/class/net', str(net)),
        ('/usr/bin/nc', str(base / 'mock-nc')),
        ('/bin/boot-proof-reboot', str(base / 'mock-reboot')),
    ):
        if original not in script:
            raise ValueError('Source substitution absent: ' + original)
        script = script.replace(original, replacement)
    (base / 'wifi-runtime.sh').write_text(script)
    (base / 'mock-reboot').write_text(
        '#!/bin/sh\necho REBOOT_REQUESTED >> ' + str(base / 'events') + '\n')
    (base / 'mock-reboot').chmod(0o700)
    (base / 'mock-nc').write_text(
        '#!/bin/sh\nprintf "TARGET=%s\\n" "$*" >> ' + str(base / 'events') +
        '\ncat >> ' + str(base / 'events') + '\n')
    (base / 'mock-nc').chmod(0o700)
    worker = (
        'bash -c "exec -a /usr/sbin/dropbear sleep 60" &\n'
        f'echo $! > {run}/ssh.pid\n'
        f'echo 192.168.100.42 > {run}/address\n'
        f'echo wlan0 > {run}/interface\n'
        f'echo ready > {run}/ssh-ready\n'
        'return 0\n'
    ) if success else 'return 132\n'
    harness = (
        '#!/bin/sh\nBB=/usr/bin/busybox\n'
        f'log() {{ echo "$*" >> {base}/events; }}\n'
        f'. {base}/wifi-runtime.sh\n'
        'lynx_wifi_worker() {\n' + worker + '}\n'
        'lynx_wifi_supervise\n'
    )
    (base / 'harness.sh').write_text(harness)
    try:
        completed = subprocess.run(['sh', str(base / 'harness.sh')],
                                   capture_output=True, text=True, timeout=12)
        events = (base / 'events').read_text()
        if success:
            if (completed.returncode or
                    'MINIMAL_LOCAL_SSH_READY interface=wlan0 address=192.168.100.42' not in events or
                    'LYNX_HELLO fixture-token' not in events or
                    'REBOOT_REQUESTED' in events):
                raise AssertionError('V27a success decision failed: ' + events)
        elif (completed.returncode == 0 or 'WIFI_WORKER_FAILED status=132' not in events or
              events.count('REBOOT_REQUESTED') != 1 or 'LYNX_HELLO' in events):
            raise AssertionError('V27a failure decision failed: ' + events)
        return {'case': 'success' if success else 'worker-failure',
                'exit_code': completed.returncode, 'events': events.splitlines()}
    finally:
        pidfile = run / 'ssh.pid'
        if pidfile.exists():
            try:
                os.kill(int(pidfile.read_text().strip()), signal.SIGTERM)
            except (ValueError, ProcessLookupError):
                pass


def main():
    os.umask(0o077)
    script = packaged_script()
    with tempfile.TemporaryDirectory(prefix='lynx-v27a-wifi-', dir=PORT / 'artifacts') as temp:
        cases = [scenario(Path(temp), script, True),
                 scenario(Path(temp), script, False)]
    out = PORT / 'artifacts' / ('v27a-wifi-fixture-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    report = {'state': 'passed', 'cases': cases, 'phone_contacted': False,
              'flash_performed': False,
              'limits': 'Fake network and Dropbear. No handset boot or timer proof.'}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(out / 'result.json')}))


if __name__ == '__main__':
    main()
