"""Record an actual native build inside Lynx's separate Alpine compiler root."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
IP = '192.168.100.8'
BOOT_ID = '9054078d-aafa-4abf-9600-5c70f8234360'
INIT_SHA = 'ebc6bb746aaf710d915c47036f92ce0c4ed23a185dfb5349b90e654bab7ba4ae'
DEVROOT = '/var/lib/lynx-devroot'


def main():
    os.umask(0o077)
    out = ROOT / 'logs' / f'v47-isolated-toolchain-proof-{time.time_ns()}'
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'boot_id': BOOT_ID, 'devroot': DEVROOT,
              'boot_partition_writes': False, 'host_libc_upgrade': False,
              'steps': []}

    def step(name, command, port=2222, timeout=35):
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
        state = step('host_and_root_state',
            'set -eu; '
            f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
            'test "$(readlink /proc/1/exe)" = /sbin/openrc-init; '
            'grep -qx musl=1.2.6-r2 /etc/apk/world; '
            'grep -qx musl-utils=1.2.6-r2 /etc/apk/world; '
            f'apk --root {DEVROOT} info -e musl musl-dev gcc make binutils '
            'busybox build-base >/dev/null; '
            'test "$(df -Pm / | awk \'NR==2 {print $4}\')" -ge 350; '
            'for s in lynx-health lynx-battery-reserve lynx-local-logs '
            'lynx-wifi lynx-dropbear lynx-maintenance lynx-time-sync '
            'lynx-power-history; do /sbin/rc-service "$s" status >/dev/null; done; '
            f'chroot {DEVROOT} /usr/bin/gcc --version; '
            f'chroot {DEVROOT} /usr/bin/make --version; '
            'printf LYNX_ISOLATED_TOOLCHAIN_READY')
        if 'LYNX_ISOLATED_TOOLCHAIN_READY' not in state:
            raise RuntimeError('isolated toolchain marker absent')
        source = '#include <stdio.h>\nint main(void){puts("LYNX_ISOLATED_NATIVE_BUILD_OK");return 0;}\n'
        command = (
            'set -eu; '
            f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
            f'mkdir -p {DEVROOT}/tmp; '
            f"cat > {DEVROOT}/tmp/proof.c <<'LYNX_SOURCE'\n" + source +
            'LYNX_SOURCE\n' +
            f'chroot {DEVROOT} /usr/bin/gcc -O2 -o /tmp/proof /tmp/proof.c; '
            f'chroot {DEVROOT} /tmp/proof')
        if step('native_build', command, timeout=60) != 'LYNX_ISOLATED_NATIVE_BUILD_OK\n':
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
