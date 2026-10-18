"""Check V25 local Wi-Fi success/failure decisions with fake devices only."""
import json
import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'linux-port/lynx-wifi-local-supervise.sh'


def scenario(parent, success):
    base = parent / ('success' if success else 'failure')
    run = base / 'run/lynx'
    net = base / 'sys/class/net'
    config = base / 'etc/lynx'
    run.mkdir(parents=True)
    (net / 'wlan0').mkdir(parents=True)
    config.mkdir(parents=True)
    (config / 'host-ip').write_text('192.168.100.106\n')
    (config / 'session-token').write_text('fixture-token\n')
    source = SOURCE.read_text()
    for original, replacement in (
        ('/run/lynx', str(run)),
        ('/sys/class/net', str(net)),
        ('/etc/lynx', str(config)),
        ('/usr/bin/nc', str(base / 'mock-nc')),
        ('/bin/boot-proof-reboot', str(base / 'mock-reboot')),
    ):
        if original not in source:
            raise ValueError('Source substitution absent: ' + original)
        source = source.replace(original, replacement)
    (base / 'supervisor.sh').write_text(source)
    (base / 'mock-reboot').write_text('#!/bin/sh\necho REBOOT_REQUESTED >> ' + str(base / 'events') + '\n')
    (base / 'mock-reboot').chmod(0o700)
    (base / 'mock-nc').write_text('#!/bin/sh\nprintf "BEACON_TARGET=%s\\n" "$*" >> ' +
                                  str(base / 'events') + '\ncat >> ' + str(base / 'events') + '\n')
    (base / 'mock-nc').chmod(0o700)
    worker = (
        'bash -c "exec -a /usr/sbin/dropbear sleep 60" &\n'
        f'echo $! > {run}/ssh.pid\n'
        f'echo 192.168.100.7 > {run}/address\n'
        f'echo wlan0 > {run}/interface\n'
        f'echo ready > {run}/ssh-ready\n'
        'return 0\n'
    ) if success else 'return 132\n'
    harness = (
        '#!/bin/sh\nBB=/usr/bin/busybox\n'
        f'log() {{ echo "$*" >> {base}/events; }}\n'
        "lynx_clock() { IFS=' ' read -r raw unused < /proc/uptime; seconds=${raw%%.*}; }\n"
        'lynx_wifi_worker() {\n' + worker + '}\n'
        f'. {base}/supervisor.sh\nlynx_wifi_supervise_local\n'
    )
    (base / 'harness.sh').write_text(harness)
    try:
        completed = subprocess.run(['sh', str(base / 'harness.sh')], capture_output=True,
                                   text=True, timeout=8)
        events = (base / 'events').read_text()
        if success:
            if (completed.returncode or 'LOCAL_WIFI_SSH_READY' not in events or
                    'LYNX_HELLO fixture-token' not in events or
                    'BEACON_TARGET=-u -w 1 192.168.100.106 5514' not in events or
                    'REBOOT_REQUESTED' in events):
                raise AssertionError('Local Wi-Fi success decision failed: ' + events)
        else:
            if (completed.returncode == 0 or 'WORKER_FAILED status=132' not in events or
                    events.count('REBOOT_REQUESTED') != 1 or 'LYNX_HELLO' in events):
                raise AssertionError('Local Wi-Fi failure did not return once: ' + events)
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
    with tempfile.TemporaryDirectory(prefix='lynx-local-wifi-', dir=ROOT / 'linux-port/artifacts') as temp:
        base = Path(temp)
        cases = [scenario(base, True), scenario(base, False)]
    out = ROOT / 'linux-port/artifacts' / ('wifi-local-supervisor-check-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    result = {'state': 'passed', 'cases': cases, 'phone_contacted': False,
              'flash_performed': False,
              'limits': 'Fake network, fake Dropbear and fake reboot; no handset proof.'}
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'state': 'passed', 'result': str(out / 'result.json')}))


if __name__ == '__main__':
    main()
