"""Create a removable native compiler root without changing Lynx's base libc."""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
IP = '192.168.100.8'
BOOT_ID = '9054078d-aafa-4abf-9600-5c70f8234360'
INIT_SHA = 'ebc6bb746aaf710d915c47036f92ce0c4ed23a185dfb5349b90e654bab7ba4ae'
DEVROOT = '/var/lib/lynx-devroot'
APK = 'apk --root ' + DEVROOT + ' --no-cache'
ADD_FLAGS = '--scripts=no --commit-hooks=no'


def main():
    os.umask(0o077)
    out = ROOT / 'logs' / f'v47-isolated-toolchain-{time.time_ns()}'
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'boot_id': BOOT_ID, 'devroot': DEVROOT,
              'boot_partition_writes': False, 'host_libc_upgrade': False,
              'steps': []}

    def step(name, command, timeout=35, port=2222):
        argv = ssh_command(IP, command)
        argv[-2:-2] = ['-p', str(port)]
        run = subprocess.run(argv, capture_output=True, timeout=timeout)
        (out / f'{name}.stdout').write_bytes(run.stdout)
        (out / f'{name}.stderr').write_bytes(run.stderr)
        report['steps'].append({
            'name': name, 'exit_code': run.returncode,
            'stdout_sha256': hashlib.sha256(run.stdout).hexdigest(),
            'stderr_sha256': hashlib.sha256(run.stderr).hexdigest()})
        if run.returncode:
            raise RuntimeError(f'{name} failed; inspect saved streams')
        return run.stdout.decode(errors='replace')

    try:
        step('rescue_identity',
             'set -eu; '
             f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
             f'test "$(sha256sum /init | cut -c1-64)" = "{INIT_SHA}"; '
             'printf LYNX_V47_RESCUE_VERIFIED', port=22)
        ready = step('preflight',
            'set -eu; '
            f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
            'test "$(readlink /proc/1/exe)" = /sbin/openrc-init; '
            'test "$(cat /etc/alpine-release)" = 3.24.2; '
            'test "$(awk \'$2=="/" {print $3; exit}\' /proc/mounts)" = ext4; '
            f'test ! -e {DEVROOT}/lib/apk/db/installed; '
            'test "$(df -Pm / | awk \'NR==2 {print $4}\')" -ge 700; '
            'test "$(date -u +%Y)" = 2026; '
            'chronyc tracking | grep -q "Leap status *: Normal"; '
            'for s in lynx-health lynx-battery-reserve lynx-local-logs '
            'lynx-wifi lynx-dropbear lynx-maintenance lynx-time-sync '
            'lynx-power-history; do /sbin/rc-service "$s" status >/dev/null; done; '
            'grep -qx musl=1.2.6-r2 /etc/apk/world; '
            'grep -qx musl-utils=1.2.6-r2 /etc/apk/world; '
            'sample=$(cat /sys/bus/i2c/devices/7-0055/battery_snapshot); '
            'printf "%s\n" "$sample" | grep -qx capacity_error=0; '
            'printf "%s\n" "$sample" | grep -qx temperature_error=0; '
            'capacity=$(printf "%s\n" "$sample" | sed -n "s/^capacity_percent=//p"); '
            'temp=$(printf "%s\n" "$sample" | sed -n "s/^temperature_millidegrees_celsius=//p"); '
            'case "$capacity:$temp" in *[!0-9:]*|::*|*::*) exit 1;; esac; '
            'test "$capacity" -ge 70; test "$temp" -ge 10000; '
            'test "$temp" -lt 35000; '
            'printf "LYNX_DEVROOT_READY capacity=%s temp_mC=%s\n" "$capacity" "$temp"')
        if not re.fullmatch(r'LYNX_DEVROOT_READY capacity=\d+ temp_mC=\d+\n', ready):
            raise RuntimeError('preflight marker absent')
        report['battery_preflight'] = ready.strip()
        step('prepare_root',
             f'set -eu; mkdir -p {DEVROOT}/etc/apk/keys; '
             f'cp /etc/apk/keys/* {DEVROOT}/etc/apk/keys/; '
             f'cp /etc/apk/repositories {DEVROOT}/etc/apk/repositories; '
             f'chmod 700 {DEVROOT}; '
             f'test "$(find {DEVROOT}/etc/apk/keys -type f | wc -l)" -ge 1; '
             'printf LYNX_DEVROOT_PREPARED')
        step('initdb', APK + ' add --initdb ' + ADD_FLAGS, timeout=45)
        # All package writes stay below DEVROOT; scripts and hooks are
        # disabled, while the copied Alpine public keys still verify APKs.
        step('simulate', APK + ' add ' + ADD_FLAGS + ' --simulate busybox build-base', timeout=65)
        step('install', APK + ' add ' + ADD_FLAGS + ' busybox build-base', timeout=240)
        proof = step('verify',
            'set -eu; '
            f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
            'grep -qx musl=1.2.6-r2 /etc/apk/world; '
            'grep -qx musl-utils=1.2.6-r2 /etc/apk/world; '
            f'{APK} info -e musl musl-dev gcc make binutils busybox >/dev/null; '
            f'test "$(df -Pm / | awk \'NR==2 {{print $4}}\')" -ge 350; '
            'for s in lynx-health lynx-battery-reserve lynx-local-logs '
            'lynx-wifi lynx-dropbear lynx-maintenance lynx-time-sync '
            'lynx-power-history; do /sbin/rc-service "$s" status >/dev/null; done; '
            f'chroot {DEVROOT} /usr/bin/gcc --version; '
            f'chroot {DEVROOT} /usr/bin/make --version; '
            'printf LYNX_DEVROOT_VERIFIED', timeout=35)
        if 'LYNX_DEVROOT_VERIFIED' not in proof:
            raise RuntimeError('devroot proof absent')
        source = '#include <stdio.h>\nint main(void){puts("LYNX_ISOLATED_NATIVE_BUILD_OK");return 0;}\n'
        build = (
            'set -eu; '
            f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
            f'mkdir -p {DEVROOT}/tmp; '
            f"cat > {DEVROOT}/tmp/proof.c <<'LYNX_SOURCE'\n" + source +
            'LYNX_SOURCE\n' +
            f'chroot {DEVROOT} /usr/bin/gcc -O2 -o /tmp/proof /tmp/proof.c; '
            f'chroot {DEVROOT} /tmp/proof')
        built = step('native_build', build, timeout=60)
        if built != 'LYNX_ISOLATED_NATIVE_BUILD_OK\n':
            raise RuntimeError('native binary output mismatch')
        report['state'] = 'v47-isolated-native-toolchain-proven'
    except Exception as exc:
        report.update(state='failed-or-incomplete', error=str(exc))
    report['finished_ns'] = time.time_ns()
    result = out / 'result.json'
    result.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(result)}))
    if report['state'] != 'v47-isolated-native-toolchain-proven':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
