"""Guarded rescue-SSH rollback of Lynx's staged charging-aware reserve script."""

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from capture_v34_health_window import matching_host, open_ssh_hosts
from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / 'linux-port/lynx-battery-reserve.sh'
INIT_SHA = 'ebc6bb746aaf710d915c47036f92ce0c4ed23a185dfb5349b90e654bab7ba4ae'
TARGET = '/run/lynx/persistent-alpine/usr/libexec/lynx-battery-reserve.sh'
BACKUP = '/run/lynx/persistent-alpine/root/lynx-rescue/battery-reserve-unplugged-v46.sh'
BOOT_RE = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage-result', required=True, type=Path)
    choices = parser.add_mutually_exclusive_group(required=True)
    choices.add_argument('--prepare', action='store_true')
    choices.add_argument('--apply', action='store_true')
    parser.add_argument('--prepared', type=Path)
    args = parser.parse_args()
    stage_path = args.stage_result.resolve(strict=True)
    if not stage_path.is_relative_to(ROOT / 'logs'):
        raise ValueError('Stage receipt outside Lynx logs')
    stage = json.loads(stage_path.read_text())
    old_sha, new_sha = stage['old_sha256'], stage['new_sha256']
    if (stage.get('state') != 'v46-charging-reserve-staged-for-next-boot' or
            stage.get('rescue_ssh_verified') is not True or
            new_sha != sha(SCRIPT.read_bytes()) or
            not re.fullmatch(r'[0-9a-f]{64}', old_sha) or
            not BOOT_RE.fullmatch(stage['boot_id'])):
        raise ValueError('Verified charging-reserve stage receipt missing')
    if args.apply and args.prepared is None:
        parser.error('--apply requires --prepared')
    if args.prepare and args.prepared is not None:
        parser.error('--prepared applies only to --apply')

    ip = matching_host(asyncio.run(open_ssh_hosts()))
    if ip is None:
        raise ValueError('Pinned Lynx rescue SSH not found')
    argv_prefix = ssh_command(ip, '')
    os.umask(0o077)
    out = ROOT / 'logs' / f'v46-reserve-rollback-{time.time_ns()}'
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'stage_result': str(stage_path),
              'phone_ip': ip, 'old_sha256': old_sha, 'new_sha256': new_sha,
              'boot_partition_writes': False, 'phone_writes': args.apply,
              'mode': 'apply' if args.apply else 'prepare'}

    def remote(name, command):
        argv = argv_prefix[:-1] + [command]
        run = subprocess.run(argv, capture_output=True, timeout=20)
        (out / f'{name}.stdout').write_bytes(run.stdout)
        (out / f'{name}.stderr').write_bytes(run.stderr)
        if run.returncode:
            raise ValueError(f'{name} failed; inspect private streams')
        return run.stdout.decode(errors='replace')

    preflight = (
        'set -eu; '
        f'test "$(sha256sum /init | cut -c1-64)" = "{INIT_SHA}"; '
        'boot_id=$(cat /proc/sys/kernel/random/boot_id); '
        'test -d /run/lynx/persistent-alpine; '
        'test "$(awk \'$2=="/run/lynx/persistent-alpine" {print $3; exit}\' /proc/mounts)" = ext4; '
        f'test "$(sha256sum {TARGET} | cut -c1-64)" = "{new_sha}"; '
        f'test "$(sha256sum {BACKUP} | cut -c1-64)" = "{old_sha}"; '
        'printf "LYNX_RESERVE_ROLLBACK_READY boot_id=%s\\n" "$boot_id"'
    )
    try:
        output = remote('preflight', preflight)
        match = re.search(r'LYNX_RESERVE_ROLLBACK_READY boot_id=([0-9a-f-]{36})', output)
        if not match or not BOOT_RE.fullmatch(match.group(1)):
            raise ValueError('Same-boot rollback proof missing')
        boot_id = match.group(1)
        report['boot_id'] = boot_id
        if args.prepare:
            report['state'] = 'v46-reserve-rollback-prepared'
        else:
            prepared_path = args.prepared.resolve(strict=True)
            if not prepared_path.is_relative_to(ROOT / 'logs'):
                raise ValueError('Prepared receipt outside Lynx logs')
            prepared = json.loads(prepared_path.read_text())
            if (prepared.get('state') != 'v46-reserve-rollback-prepared' or
                    prepared.get('stage_result') != str(stage_path) or
                    prepared.get('boot_id') != boot_id or
                    prepared.get('phone_ip') != ip):
                raise ValueError('Fresh same-boot rollback preparation required')
            command = (
                preflight + '; '
                f'cp -p {BACKUP} {TARGET}.restore; '
                f'test "$(sha256sum {TARGET}.restore | cut -c1-64)" = "{old_sha}"; '
                f'mv {TARGET}.restore {TARGET}; '
                f'test "$(sha256sum {TARGET} | cut -c1-64)" = "{old_sha}"; '
                'printf LYNX_RESERVE_ROLLBACK_APPLIED'
            )
            if 'LYNX_RESERVE_ROLLBACK_APPLIED' not in remote('apply', command):
                raise ValueError('Rollback completion marker missing')
            report['state'] = 'v46-reserve-rollback-applied-for-next-boot'
    except Exception as error:
        report.update(state='failed-or-incomplete', error=str(error))
    report['finished_ns'] = time.time_ns()
    result = out / 'result.json'
    result.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(result)}))
    if report['state'] not in ('v46-reserve-rollback-prepared',
                               'v46-reserve-rollback-applied-for-next-boot'):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
