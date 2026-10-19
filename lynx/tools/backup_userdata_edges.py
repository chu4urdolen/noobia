"""Read-only Lynx userdata edge backup over pinned SSH; no phone writes."""
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
BLOCK = 1024 * 1024
COUNT = 16
PARTITION_SECTORS = 466026432
PARTITION_BYTES = PARTITION_SECTORS * 512


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(BLOCK), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ip', default='192.168.100.4',
                        help='Lynx lease on the isolated Noobia Wi-Fi')
    args = parser.parse_args()
    if ipaddress.ip_address(args.ip) not in ipaddress.ip_network('192.168.100.0/24'):
        parser.error('IP must be on the isolated Noobia Wi-Fi')
    ip = args.ip
    os.umask(0o077)
    out = ROOT / 'backups' / ('userdata-edges-' + str(time.time_ns()))
    out.mkdir(parents=True, mode=0o700)
    result = {'state': 'starting', 'created_ns': time.time_ns(),
              'partition': 'userdata', 'device': '/dev/sdc85',
              'size_bytes': PARTITION_BYTES, 'phone_partition_writes': False,
              'phone_mounts': False, 'host_backup_dir': str(out), 'parts': []}

    def save():
        temp = out / 'result.tmp'
        temp.write_text(json.dumps(result, indent=2) + '\n')
        temp.replace(out / 'result.json')

    save()
    try:
        proof = subprocess.run(ssh_command(ip, PROOF), capture_output=True, timeout=15)
        (out / 'identity.stdout').write_bytes(proof.stdout)
        (out / 'identity.stderr').write_bytes(proof.stderr)
        if not proof_valid(proof.stdout.decode(errors='replace'), proof.returncode):
            raise ValueError('Pinned Lynx identity refused')
        preflight = '''set -eu
grep -Fx 'PARTNAME=userdata' /sys/class/block/sdc85/uevent >/dev/null
[ "$(cat /sys/class/block/sdc85/size)" = 466026432 ]
[ "$(cat /sys/class/block/sdc/queue/logical_block_size)" = 4096 ]
[ -b /dev/sdc85 ]
! grep -Eq '^/dev/sdc85 |^/dev/block/by-name/userdata ' /proc/mounts
[ "$(cat /run/lynx/health-bootstrap/ready)" = ready ]
/bin/busybox sh /run/lynx/lynx-health-supervisor.sh --once
cat /proc/sys/kernel/random/boot_id'''
        check = subprocess.run(ssh_command(ip, preflight), capture_output=True, timeout=15)
        (out / 'preflight.stdout').write_bytes(check.stdout)
        (out / 'preflight.stderr').write_bytes(check.stderr)
        if check.returncode:
            raise ValueError('Read-only partition or health preflight refused')
        result['boot_id'] = check.stdout.decode().strip().splitlines()[-1]
        save()
        for name, block_size, skip, count in [
                ('head', BLOCK, 0, COUNT),
                ('tail', 4096, PARTITION_BYTES // 4096 - BLOCK * COUNT // 4096,
                 BLOCK * COUNT // 4096)]:
            path = out / (name + '-16MiB.bin')
            command = (f'[ "$(cat /proc/sys/kernel/random/boot_id)" = '
                       f'{result["boot_id"]} ] && '
                       f'/bin/busybox dd if=/dev/sdc85 bs={block_size} '
                       f'skip={skip} count={count} 2>/dev/null')
            with path.open('wb') as stream:
                read = subprocess.run(ssh_command(ip, command),
                                      stdout=stream, stderr=subprocess.PIPE,
                                      timeout=90)
            (out / (name + '.stderr')).write_bytes(read.stderr)
            if read.returncode or path.stat().st_size != BLOCK * COUNT:
                raise ValueError(name + ' read failed or was short')
            result['parts'].append({'name': name, 'offset_bytes': skip * block_size,
                                    'bytes': path.stat().st_size,
                                    'sha256': digest(path), 'path': str(path)})
            save()
        result['state'] = 'verified-read-only-backup'
    except Exception as error:
        result.update(state='failed', error=str(error))
    result['finished_ns'] = time.time_ns()
    save()
    print(json.dumps({'state': result['state'], 'result': str(out / 'result.json')}))
    if result['state'] != 'verified-read-only-backup':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
