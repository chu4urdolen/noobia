"""Copy and verify Lynx's checksummed early-boot stage logs over pinned SSH."""

import argparse
import base64
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
BOOT_ID = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')
FRAME = re.compile(rb'FILE ([0-9a-f-]{36}\.log) ([0-9]+) ([0-9a-f]{64})\n'
                   rb'([A-Za-z0-9+/=]*)\nEND\n')
REMOTE = '''set -eu
test "$(readlink /proc/1/exe)" = /sbin/openrc-init
test "$(cat /etc/alpine-release)" = 3.24.2
test "$(awk '$2=="/" {print $3; exit}' /proc/mounts)" = ext4
dir=/var/log/lynx-bootdiag
test -d "$dir" && test ! -L "$dir" || { printf 'NO_LOG_DIR\\n'; exit 0; }
count=0
for file in "$dir"/*.log; do
    test -f "$file" && test ! -L "$file" || continue
    name=${file##*/}
    stem=${name%.log}
    case "$stem" in *[!0-9a-f-]*|'') exit 1;; esac
    test "${#stem}" -eq 36
    bytes=$(/bin/busybox wc -c < "$file")
    case "$bytes" in ''|*[!0-9]*) exit 1;; esac
    test "$bytes" -le 4096
    digest=$(/bin/busybox sha256sum "$file")
    digest=${digest%% *}
    printf 'FILE %s %s %s\\n' "$name" "$bytes" "$digest"
    /bin/busybox base64 -w 0 "$file"
    printf '\\nEND\\n'
    count=$((count+1))
    test "$count" -le 256
done
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verification', required=True, type=Path)
    args = parser.parse_args()
    verified = args.verification.resolve(strict=True)
    if not verified.is_relative_to(ROOT / 'logs'):
        raise ValueError('Verification outside Lynx logs')
    proof = json.loads(verified.read_text())
    boot_id, ip = proof['boot_id'], proof['phone_ip']
    if (proof.get('state') != 'v46-autonomous-alpine-pid1-verified' or
            not BOOT_ID.fullmatch(boot_id) or
            not re.fullmatch(r'192\.168\.100\.[1-9][0-9]?', ip)):
        raise ValueError('Exact V46 same-boot proof missing')
    os.umask(0o077)
    out = ROOT / 'logs' / f'v46-bootdiag-capture-{time.time_ns()}'
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'verification': str(verified),
              'boot_id': boot_id, 'phone_ip': ip,
              'phone_writes': False, 'records': []}
    command = ('test "$(cat /proc/sys/kernel/random/boot_id)" = "' +
               boot_id + '" && ' + REMOTE)
    argv = ssh_command(ip, command)
    argv[-2:-2] = ['-p', '2222']
    try:
        run = subprocess.run(argv, capture_output=True, timeout=30)
        (out / 'capture.stdout').write_bytes(run.stdout)
        (out / 'capture.stderr').write_bytes(run.stderr)
        if run.returncode or len(run.stdout) > 2_000_000:
            raise ValueError('Bounded bootdiag transfer failed')
        if run.stdout == b'NO_LOG_DIR\n':
            report['state'] = 'no-log-directory'
        else:
            records = out / 'records'
            records.mkdir(mode=0o700)
            cursor = 0
            while cursor < len(run.stdout):
                match = FRAME.match(run.stdout, cursor)
                if not match:
                    raise ValueError('Malformed bootdiag frame')
                name, count, digest, encoded = match.groups()
                data = base64.b64decode(encoded, validate=True)
                if len(data) != int(count) or hashlib.sha256(data).hexdigest().encode() != digest:
                    raise ValueError('Bootdiag frame hash or size differs')
                path = records / name.decode()
                if path.exists():
                    raise ValueError('Duplicate bootdiag ID')
                path.write_bytes(data)
                report['records'].append(parse(path))
                cursor = match.end()
            report['state'] = 'v46-bootdiag-records-verified'
    except Exception as error:
        report.update(state='failed-or-incomplete', error=str(error))
    report['finished_ns'] = time.time_ns()
    result = out / 'result.json'
    result.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(result),
                      'records': len(report['records']),
                      'charger_on': sum(any(e['stage'] == 'CHARGER_ON' for e in item['events'])
                                        for item in report['records'])}))
    if report['state'] == 'failed-or-incomplete':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
