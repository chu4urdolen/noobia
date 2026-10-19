"""Sample unmounted Lynx userdata read-only to inform a storage decision."""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import PROOF, proof_valid, ssh_command


ROOT = Path(__file__).resolve().parent.parent
BLOCK = 1048576
OFFSETS_MIB = (1, 16, 64, 256, 1024, 4096, 16384, 32768,
               65536, 100000, 150000, 200000, 227000)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ip', default='192.168.100.4')
    args = parser.parse_args()
    if ipaddress.ip_address(args.ip) not in ipaddress.ip_network('192.168.100.0/24'):
        parser.error('IP must be on the isolated Noobia Wi-Fi')
    os.umask(0o077)
    out = ROOT / 'backups' / ('userdata-samples-' + str(time.time_ns()))
    out.mkdir(parents=True, mode=0o700)
    report = {'state': 'starting', 'created_ns': time.time_ns(),
              'device': '/dev/sdc85', 'sample_bytes': BLOCK,
              'offsets_mib': OFFSETS_MIB, 'phone_writes': False,
              'phone_mounts': False, 'samples': []}

    def save():
        temp = out / 'result.tmp'
        temp.write_text(json.dumps(report, indent=2) + '\n')
        temp.replace(out / 'result.json')

    save()
    try:
        identity = subprocess.run(ssh_command(args.ip, PROOF),
                                  capture_output=True, timeout=15)
        if not proof_valid(identity.stdout.decode(errors='replace'), identity.returncode):
            raise ValueError('Pinned Lynx identity refused')
        guard = '''set -eu
grep -Fx 'PARTNAME=userdata' /sys/class/block/sdc85/uevent >/dev/null
[ "$(cat /sys/class/block/sdc85/size)" = 466026432 ]
[ -b /dev/sdc85 ]
! grep -Eq '^/dev/sdc85 |^/dev/block/by-name/userdata ' /proc/mounts
/bin/busybox sh /run/lynx/lynx-health-supervisor.sh --once
cat /proc/sys/kernel/random/boot_id'''
        check = subprocess.run(ssh_command(args.ip, guard),
                               capture_output=True, timeout=15)
        if check.returncode:
            raise ValueError('Partition or health guard refused')
        boot_id = check.stdout.decode().strip().splitlines()[-1]
        report['boot_id'] = boot_id
        save()
        commands = [f'[ "$(cat /proc/sys/kernel/random/boot_id)" = {boot_id} ]']
        commands += [f'/bin/busybox dd if=/dev/sdc85 bs={BLOCK} skip={n} '
                     'count=1 2>/dev/null' for n in OFFSETS_MIB]
        raw_path = out / 'samples-concatenated.bin'
        with raw_path.open('wb') as destination:
            read = subprocess.run(ssh_command(args.ip, ' && '.join(commands)),
                                  stdout=destination, stderr=subprocess.PIPE,
                                  timeout=120)
        (out / 'read.stderr').write_bytes(read.stderr)
        if read.returncode or raw_path.stat().st_size != len(OFFSETS_MIB) * BLOCK:
            raise ValueError('Sample stream failed or was short')
        with raw_path.open('rb') as source:
            for offset in OFFSETS_MIB:
                sample = source.read(BLOCK)
                report['samples'].append({
                    'offset_bytes': offset * BLOCK,
                    'zero_bytes': sample.count(0),
                    'sha256': hashlib.sha256(sample).hexdigest()})
        report['stream_sha256'] = hashlib.sha256(raw_path.read_bytes()).hexdigest()
        report['state'] = 'verified-read-only-samples'
    except Exception as error:
        report.update(state='failed', error=str(error))
    report['finished_ns'] = time.time_ns()
    save()
    print(json.dumps({'state': report['state'], 'result': str(out / 'result.json')}))
    if report['state'] != 'verified-read-only-samples':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
