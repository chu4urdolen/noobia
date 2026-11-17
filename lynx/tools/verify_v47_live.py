"""Verify V47's actual Alpine handoff, services, and boot record over pinned SSH."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command
from parse_v38_persistent_trace import parse


ROOT = Path(__file__).resolve().parent.parent
V47_SHA = 'c969e1938b051ab03b49ad4f2260e900e9e336997d1026ca00c3a493dedde066'
V46_SHA = '6c487df1c16af1717e045167c165271065e9060c5a02b16b8e1b3ce3eca28f91'
V46 = ROOT / 'linux-port/artifacts/persistent-alpine-v46-offline/nord3-persistent-alpine-v46-untested.img'
OLD_BOOT = 'f6230cac-8d41-48da-bf28-2700e9ff56f1'
OLD_LOG_MARKER = 'LYNX_LOG_PROOF_1792783769273304739'
BOOT_ID = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collector', required=True, type=Path)
    args = parser.parse_args()
    path = args.collector.resolve(strict=True)
    if not path.is_relative_to(ROOT / 'logs'):
        raise ValueError('Collector outside Lynx logs')
    collector = json.loads(path.read_text())
    build = json.loads((ROOT / 'linux-port/artifacts/wifi-dhcp-retry-v47-offline/build-result.json').read_text())
    ip = collector.get('pinned_ip')
    if (collector.get('image_sha256') != V47_SHA or
            not collector.get('candidate_seen') or
            not collector.get('alpine_pid1_seen') or
            not re.fullmatch(r'192\.168\.100\.[1-9][0-9]?', str(ip)) or
            hashlib.sha256(V46.read_bytes()).hexdigest() != V46_SHA):
        raise ValueError('V47 observer or V46 restoration missing')
    candidates = [(index + 1, sample) for index, sample in enumerate(collector['samples'])
                  if sample.get('init_match') and sample.get('wifi_match') and
                  sample.get('alpine_pid1_match') and sample.get('exit_code') == 0]
    if not candidates:
        raise ValueError('No complete V47 Alpine sample')
    number, _ = candidates[-1]
    raw = (path.parent / f'sample-{number}.raw').read_bytes()
    match = re.search(rb'^BOOT_ID=([0-9a-f-]{36})$', raw, re.M)
    if not match or not BOOT_ID.fullmatch(match.group(1).decode()):
        raise ValueError('Boot ID absent from pinned sample')
    boot_id = match.group(1).decode()
    os.umask(0o077)
    out = ROOT / 'logs' / f'v47-live-verify-{time.time_ns()}'
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'boot_id': boot_id, 'phone_ip': ip,
              'collector': str(path), 'image_sha256': V47_SHA,
              'restoration_v46_sha256': V46_SHA, 'phone_writes': False,
              'steps': []}

    def step(name, command, port=22):
        argv = ssh_command(ip, command)
        if port != 22:
            argv[-2:-2] = ['-p', str(port)]
        run = subprocess.run(argv, capture_output=True, timeout=20)
        (out / f'{name}.stdout').write_bytes(run.stdout)
        (out / f'{name}.stderr').write_bytes(run.stderr)
        report['steps'].append({'name': name, 'port': port,
                                'exit_code': run.returncode,
                                'stdout_sha256': hashlib.sha256(run.stdout).hexdigest()})
        if run.returncode:
            raise RuntimeError(f'{name} failed; see saved streams')
        return run.stdout

    try:
        rescue = step('rescue_identity',
                      'set -eu; '
                      f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}"; '
                      'sha256sum /init /etc/lynx/wifi-runtime.sh')
        if (build['init_sha256'].encode() + b'  /init' not in rescue or
                build['new_wifi_sha256'].encode() +
                b'  /etc/lynx/wifi-runtime.sh' not in rescue):
            raise RuntimeError('V47 init or Wi-Fi script hash differs')
        alpine = step('alpine_services',
                      'set -eu; '
                      f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}"; '
                      'test "$(cat /etc/alpine-release)" = 3.24.2; '
                      'test "$(readlink /proc/1/exe)" = /sbin/openrc-init; '
                      'test "$(awk \'$2=="/" {print $3; exit}\' /proc/mounts)" = ext4; '
                      'for s in lynx-health lynx-battery-reserve lynx-local-logs lynx-wifi '
                      'lynx-dropbear lynx-maintenance lynx-time-sync lynx-power-history; do '
                      '/sbin/rc-service "$s" status >/dev/null; done; '
                      'test "$(stat -c %a /var/log/lynx/power.csv)" = 600; '
                      f'grep -q "^{boot_id}," /var/log/lynx/power.csv; '
                      'chronyc tracking | grep -q "Leap status *: Normal"; '
                      'printf LYNX_V47_ALPINE_VERIFIED', port=2222)
        if b'LYNX_V47_ALPINE_VERIFIED' not in alpine:
            raise RuntimeError('Alpine service proof absent')
        record = step('bootdiag',
                      'set -eu; '
                      f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}"; '
                      f'cat /var/log/lynx-bootdiag/{boot_id}.log', port=2222)
        if not 1 <= len(record) <= 4096:
            raise RuntimeError('Bootdiag size outside bound')
        record_path = out / f'{boot_id}.log'
        record_path.write_bytes(record)
        parsed = parse(record_path)
        stages = [entry['stage'] for entry in parsed['events']]
        if not all(stage in stages for stage in
                   ('START', 'WIFI_READY', 'HEALTH_READY',
                    'HANDOFF_BEGIN', 'TIMER_CANCELLED')):
            raise RuntimeError('V47 boot stages incomplete')
        retained = step('crossboot_retention',
                        'set -eu; '
                        f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}"; '
                        f'grep -q "^{OLD_BOOT}," /var/log/lynx/power.csv; '
                        f'grep -q "^{boot_id}," /var/log/lynx/power.csv; '
                        f'grep -Fq {OLD_LOG_MARKER} /var/log/lynx/messages*; '
                        f'test -s /var/log/lynx/boot-{OLD_BOOT}.log; '
                        'printf LYNX_V47_CROSSBOOT_VERIFIED', port=2222)
        if b'LYNX_V47_CROSSBOOT_VERIFIED' not in retained:
            raise RuntimeError('Cross-boot retention proof absent')
        report.update(state='v47-alpine-and-recovery-verified',
                      boot_stages=stages,
                      bootdiag_sha256=hashlib.sha256(record).hexdigest(),
                      previous_boot_logs_and_power_history_retained=True)
    except Exception as exc:
        report.update(state='failed-or-incomplete', error=str(exc))
    report['finished_ns'] = time.time_ns()
    result = out / 'result.json'
    result.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(result),
                      'boot_id': boot_id}))
    if report['state'] != 'v47-alpine-and-recovery-verified':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
