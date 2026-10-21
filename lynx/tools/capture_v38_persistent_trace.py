"""Read V38 stage logs from a verified V33 Alpine boot without phone writes."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from lynx_wifi_v19_contact import PROOF, proof_valid, ssh_command
from parse_v38_persistent_trace import parse

ROOT = Path(__file__).resolve().parent.parent
REMOTE = '''set -eu
grep -Fx 'PARTNAME=userdata' /sys/class/block/sdc85/uevent >/dev/null
test "$(cat /sys/class/block/sdc85/size)" = 466026432
grep -q '^/dev/sdc85 /run/lynx/persistent-alpine ext4 rw,' /proc/mounts
identity=$(/bin/busybox blkid /dev/sdc85)
case "$identity" in *'LABEL="LYNXROOT"'*'UUID="13dc3665-b062-405e-b674-ceae8972fc0f"'*'TYPE="ext4"'*) ;; *) exit 1;; esac
dir=/run/lynx/persistent-alpine/var/log/lynx-bootdiag
test -d "$dir" || { printf 'NO_LOG_DIR\\n'; exit 0; }
count=0
for file in "$dir"/*.log; do
    test -f "$file" || continue
    name=${file##*/}
    case "$name" in *.log) ;; *) exit 1;; esac
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
    test "$count" -le 32
done
'''
FRAME = re.compile(rb'FILE ([0-9a-f-]{36}\.log) ([0-9]+) ([0-9a-f]{64})\n'
                   rb'([A-Za-z0-9+/=]*)\nEND\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contact-receipt', required=True, type=Path)
    args = parser.parse_args()
    contact_path = args.contact_receipt.resolve(strict=True)
    if not contact_path.is_relative_to(ROOT / 'logs'):
        raise ValueError('Contact receipt outside Lynx logs')
    contact = json.loads(contact_path.read_text())
    if (contact.get('state') != 'native-ssh-available' or
            contact.get('native_ssh_verified') is not True or
            contact.get('fallback_cancel_ack_exit_code') != 0):
        raise ValueError('Pinned V33 contact receipt missing')
    ip = contact['phone_ip']
    os.umask(0o077)
    out = ROOT / 'logs' / ('v38-persistent-capture-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'created_ns': time.time_ns(),
              'contact_receipt': str(contact_path), 'phone_ip': ip,
              'phone_partition_writes': False, 'files': []}
    receipt = out / 'result.json'

    def save():
        temp = receipt.with_suffix('.tmp')
        temp.write_text(json.dumps(report, indent=2) + '\n')
        temp.replace(receipt)

    save()
    try:
        proof = subprocess.run(ssh_command(ip, PROOF), capture_output=True,
                               timeout=15)
        (out / 'identity.raw').write_bytes(proof.stdout + proof.stderr)
        if not proof_valid(proof.stdout.decode(errors='replace'), proof.returncode):
            raise ValueError('Pinned V33 identity differs')
        capture = subprocess.run(ssh_command(ip, REMOTE), capture_output=True,
                                 timeout=20)
        raw = capture.stdout + capture.stderr
        (out / 'capture.raw').write_bytes(raw)
        report.update(capture_exit_code=capture.returncode,
                      raw_sha256=hashlib.sha256(raw).hexdigest(), raw_bytes=len(raw))
        if capture.returncode or len(raw) > 200_000:
            raise ValueError('Read-only capture failed or exceeded bound')
        if capture.stdout == b'NO_LOG_DIR\n':
            report['state'] = 'no-log-directory'
        else:
            records = out / 'records'
            records.mkdir(mode=0o700)
            cursor = 0
            while cursor < len(capture.stdout):
                match = FRAME.match(capture.stdout, cursor)
                if not match:
                    raise ValueError('Malformed V38 capture frame')
                name, count, digest, encoded = match.groups()
                data = base64.b64decode(encoded, validate=True)
                if (len(data) != int(count) or
                        hashlib.sha256(data).hexdigest().encode() != digest):
                    raise ValueError('V38 capture frame hash/length differs')
                path = records / name.decode()
                if path.exists():
                    raise ValueError('Duplicate V38 log name')
                path.write_bytes(data)
                report['files'].append(parse(path))
                cursor = match.end()
            report['state'] = ('records-verified' if report['files'] else
                               'empty-log-directory')
    except Exception as error:
        report.update(state='failed', error=str(error))
    report['finished_ns'] = time.time_ns()
    save()
    print(json.dumps({'state': report['state'], 'result': str(receipt),
                      'files': len(report['files'])}))
    if report['state'] == 'failed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
