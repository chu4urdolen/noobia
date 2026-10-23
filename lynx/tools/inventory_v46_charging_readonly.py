"""Save a bounded, read-only charging inventory from a verified V46 Alpine boot."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
FIELDS = ('type', 'online', 'status', 'present', 'health', 'capacity',
          'temp', 'voltage_now', 'current_now')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verification', required=True, type=Path)
    args = parser.parse_args()
    path = args.verification.resolve(strict=True)
    if not path.is_relative_to(ROOT / 'logs'):
        raise ValueError('Verification must be under Lynx logs')
    proof = json.loads(path.read_text())
    boot_id, ip = proof['boot_id'], proof['phone_ip']
    if (proof.get('state') != 'v46-autonomous-alpine-pid1-verified' or
            not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', boot_id) or
            not re.fullmatch(r'192\.168\.100\.[1-9][0-9]?', ip)):
        raise ValueError('V46 verification is incomplete')

    # Only fixed sysfs attributes and /proc/modules are read on Lynx.
    remote = (
        'set -eu; '
        f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}"; '
        'test "$(cat /etc/alpine-release)" = 3.24.2; '
        'test "$(readlink /proc/1/exe)" = /sbin/openrc-init; '
        'printf "BOOT_ID %s\\n" "$(cat /proc/sys/kernel/random/boot_id)"; '
        'printf "UPTIME %s\\n" "$(cat /proc/uptime)"; '
        'for d in /sys/class/power_supply/*; do '
        '[ -d "$d" ] || continue; '
        'printf "SUPPLY %s\\n" "${d##*/}"; '
        'for field in ' + ' '.join(FIELDS) + '; do '
        '[ -r "$d/$field" ] || continue; '
        'value=$(cat "$d/$field" 2>/dev/null) || value=UNREADABLE; '
        'printf "FIELD %s %s %s\\n" "${d##*/}" "$field" "$value"; '
        'done; done; '
        'printf "MODULES_BEGIN\\n"; '
        "grep -Ei '(^|_)(mt6375|oplus_chg|tcpc|charger|battery|usb)' /proc/modules || true; "
        'printf "MODULES_END\\n"; '
        'printf "ALL_MODULES_BEGIN\\n"; '
        "awk '{print $1}' /proc/modules; "
        'printf "ALL_MODULES_END\\n"; '
        'printf "TYPEC_BEGIN\\n"; '
        'for d in /sys/class/typec/*; do [ -e "$d" ] && printf "%s\\n" "${d##*/}"; done; '
        'printf "TYPEC_END\\n"'
        '; printf "BATTERY_BEGIN\\n"; '
        'cat /sys/bus/i2c/devices/7-0055/battery_snapshot; '
        'printf "BATTERY_END\\n"; '
        'printf "ROOTFS %s\\n" "$(awk \'$2=="/" {print $3; exit}\' /proc/mounts)"; '
        'printf "RESERVE_SERVICE %s\\n" "$(test -e /etc/init.d/lynx-battery-reserve && echo present || echo absent)"'
    )
    argv = ssh_command(ip, remote)
    argv[-2:-2] = ['-p', '2222']
    os.umask(0o077)
    out = ROOT / 'logs' / f'v46-charging-readonly-{time.time_ns()}'
    out.mkdir(mode=0o700)
    receipt = {'state': 'starting', 'verification': str(path), 'boot_id': boot_id,
               'phone_ip': ip, 'read_only': True, 'port': 2222}
    try:
        run = subprocess.run(argv, capture_output=True, timeout=20)
        (out / 'stdout').write_bytes(run.stdout)
        (out / 'stderr').write_bytes(run.stderr)
        if run.returncode or len(run.stdout) > 32768:
            raise ValueError(f'SSH failed or output exceeded bound: {run.returncode}')
        lines = run.stdout.decode(errors='replace').splitlines()
        if (f'BOOT_ID {boot_id}' not in lines or 'MODULES_END' not in lines or
                'ALL_MODULES_END' not in lines or 'TYPEC_END' not in lines or
                'BATTERY_END' not in lines):
            raise ValueError('Missing same-boot marker or inventory footer')
        supplies = {}
        for line in lines:
            if line.startswith('SUPPLY '):
                supplies[line[7:]] = {}
            elif line.startswith('FIELD '):
                _, name, field, value = line.split(' ', 3)
                if name in supplies and field in FIELDS:
                    supplies[name][field] = value
        receipt.update(state='v46-charging-readonly-captured', supplies=supplies,
                       loaded_power_modules=[line.split()[0] for line in lines[
                           lines.index('MODULES_BEGIN') + 1:lines.index('MODULES_END')]],
                       loaded_modules=lines[lines.index('ALL_MODULES_BEGIN') + 1:
                                            lines.index('ALL_MODULES_END')],
                       typec_entries=lines[lines.index('TYPEC_BEGIN') + 1:lines.index('TYPEC_END')],
                       battery_snapshot=dict(line.split('=', 1) for line in lines[
                           lines.index('BATTERY_BEGIN') + 1:lines.index('BATTERY_END')]
                           if '=' in line),
                       rootfs=next((line[7:] for line in lines if line.startswith('ROOTFS ')), None),
                       reserve_service=next((line[16:] for line in lines
                                             if line.startswith('RESERVE_SERVICE ')), None))
    except Exception as error:
        receipt.update(state='failed-or-incomplete', error=str(error))
    receipt['finished_ns'] = time.time_ns()
    result = out / 'result.json'
    result.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'state': receipt['state'], 'result': str(result),
                      'supplies': receipt.get('supplies'),
                      'loaded_power_modules': receipt.get('loaded_power_modules')}))
    if receipt['state'] != 'v46-charging-readonly-captured':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
