"""Install and prove a native Alpine development toolkit on verified V47 Lynx."""

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
WIFI_SHA = 'be24ce67cbaefef63db0ba65badb69df1a2b45bb3f743e8f3877509eaf972208'
PACKAGES = ('build-base', 'curl', 'jq', 'tmux', 'rsync')


def main():
    os.umask(0o077)
    out = ROOT / 'logs' / f'v47-alpine-devkit-{time.time_ns()}'
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'boot_id': BOOT_ID, 'phone_ip': IP,
              'requested_packages': PACKAGES,
              'boot_partition_writes': False, 'steps': []}

    def step(name, command, timeout=25, port=2222):
        argv = ssh_command(IP, command)
        argv[-2:-2] = ['-p', str(port)]
        run = subprocess.run(argv, capture_output=True, timeout=timeout)
        (out / f'{name}.stdout').write_bytes(run.stdout)
        (out / f'{name}.stderr').write_bytes(run.stderr)
        report['steps'].append({'name': name, 'exit_code': run.returncode,
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
             f'test "$(sha256sum /etc/lynx/wifi-runtime.sh | cut -c1-64)" = "{WIFI_SHA}"; '
             'printf LYNX_V47_RESCUE_VERIFIED', port=22)
        ready = step('preflight',
            'set -eu; '
            f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
            'test "$(readlink /proc/1/exe)" = /sbin/openrc-init; '
            'test "$(cat /etc/alpine-release)" = 3.24.2; '
            'test "$(awk \'$2=="/" {print $3; exit}\' /proc/mounts)" = ext4; '
            'test "$(df -Pm / | awk \'NR==2 {print $4}\')" -ge 750; '
            'test "$(wc -l < /etc/apk/repositories)" -eq 2; '
            'grep -qx https://dl-cdn.alpinelinux.org/alpine/v3.24/main /etc/apk/repositories; '
            'grep -qx https://dl-cdn.alpinelinux.org/alpine/v3.24/community /etc/apk/repositories; '
            'test "$(date -u +%Y)" = 2026; '
            'chronyc tracking | grep -q "Leap status *: Normal"; '
            'for s in lynx-health lynx-battery-reserve lynx-local-logs lynx-wifi '
            'lynx-dropbear lynx-maintenance lynx-time-sync lynx-power-history; do '
            '/sbin/rc-service "$s" status >/dev/null; done; '
            'sample=$(cat /sys/bus/i2c/devices/7-0055/battery_snapshot); '
            'printf "%s\\n" "$sample" | grep -qx capacity_error=0; '
            'printf "%s\\n" "$sample" | grep -qx temperature_error=0; '
            'capacity=$(printf "%s\\n" "$sample" | sed -n "s/^capacity_percent=//p"); '
            'temp=$(printf "%s\\n" "$sample" | sed -n "s/^temperature_millidegrees_celsius=//p"); '
            'case "$capacity:$temp" in *[!0-9:]*|::*|*::*) exit 1;; esac; '
            'test "$capacity" -ge 70; test "$temp" -ge 10000; test "$temp" -lt 35000; '
            'printf "LYNX_DEVKIT_READY capacity=%s temp_mC=%s\\n" "$capacity" "$temp"')
        if not re.fullmatch(r'LYNX_DEVKIT_READY capacity=\d+ temp_mC=\d+\n', ready):
            raise RuntimeError('Preflight marker absent')
        report['battery_preflight'] = ready.strip()
        # Use the live repository index for the dry run. A cached index once
        # claimed that musl-dev-r2 was available, while the subsequent fresh
        # install selected musl-dev-r3 and correctly refused the pinned libc.
        step('simulate_fresh', 'apk add --no-cache --simulate ' + ' '.join(PACKAGES), timeout=60)
        step('install', 'apk add --no-cache ' + ' '.join(PACKAGES), timeout=180)
        proof = step('verify',
                     'set -eu; '
                     f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
                     'for package in build-base curl jq tmux rsync; do '
                     'apk info -e "$package" >/dev/null; done; '
                     'test "$(df -Pm / | awk \'NR==2 {print $4}\')" -ge 450; '
                     'for s in lynx-health lynx-battery-reserve lynx-local-logs '
                     'lynx-wifi lynx-dropbear lynx-maintenance lynx-time-sync '
                     'lynx-power-history; do /sbin/rc-service "$s" status >/dev/null; done; '
                     'gcc --version | head -n 1; make --version | head -n 1; '
                     'curl --version | head -n 1; jq --version; tmux -V; '
                     'rsync --version | head -n 1; '
                     'printf LYNX_DEVKIT_PACKAGES_VERIFIED', timeout=30)
        if 'LYNX_DEVKIT_PACKAGES_VERIFIED' not in proof:
            raise RuntimeError('Package proof absent')
        source = ('#include <stdio.h>\n'
                  'int main(void) { puts("LYNX_NATIVE_BUILD_OK"); return 0; }\n')
        # A fixed shell here-document writes only to Lynx RAM and exercises
        # native aarch64 compiler/linker output without touching boot_a.
        build_command = (
            'set -eu; '
            f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
            "cat > /run/lynx/devkit-proof.c <<'LYNX_SOURCE'\n" +
            source + 'LYNX_SOURCE\n' +
            'gcc -O2 -o /run/lynx/devkit-proof /run/lynx/devkit-proof.c; '
            '/run/lynx/devkit-proof; '
            'file /run/lynx/devkit-proof 2>/dev/null || true'
        )
        built = step('native_build', build_command, timeout=45)
        if 'LYNX_NATIVE_BUILD_OK\n' not in built:
            raise RuntimeError('Native compiled binary did not run')
        report['state'] = 'v47-native-alpine-devkit-installed-and-proven'
    except Exception as exc:
        report.update(state='failed-or-incomplete', error=str(exc))
    report['finished_ns'] = time.time_ns()
    result = out / 'result.json'
    result.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(result)}))
    if report['state'] != 'v47-native-alpine-devkit-installed-and-proven':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
