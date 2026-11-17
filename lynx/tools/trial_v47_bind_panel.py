"""Retry the deferred DSI platform probe after loading Lynx's stock panel."""

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
PANEL = 'oplus22823_tm_nt37705_fhd_dsi_cmd'


def main():
    os.umask(0o077)
    out = ROOT / 'logs' / f'v47-panel-bind-{time.time_ns()}'
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'boot_id': BOOT_ID,
              'boot_partition_writes': False, 'steps': []}

    def step(name, command, port=2222, timeout=25):
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

    def snapshot(name):
        return step(name,
            'set -eu; '
            f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
            '/usr/local/bin/lynx-status --assert-ready; '
            'printf "DRM="; ls /sys/class/drm; '
            'printf "MIPI_DEVICES="; ls /sys/bus/mipi-dsi/devices; '
            'printf "MIPI_PANEL_DRIVER="; '
            f'ls /sys/bus/mipi-dsi/drivers/{PANEL}; '
            'printf "DSI_DRIVER="; '
            'readlink /sys/bus/platform/devices/14017000.dsi/driver || :; '
            'printf "DISPSYS_DRIVER="; '
            'readlink /sys/bus/platform/devices/14000000.dispsys_config/driver || :; '
            'printf "DISPLAY_LOG="; '
            'dmesg | grep -E "mtk-dsi|TM nt37705|oplus22823|mediatek-drm|drm_dev" '
            '| tail -n 30 || :', timeout=35)

    try:
        step('rescue_identity',
             'set -eu; '
             f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
             f'test "$(sha256sum /init | cut -c1-64)" = "{INIT_SHA}"; '
             'printf LYNX_V47_RESCUE_VERIFIED', port=22)
        step('preflight',
             'set -eu; '
             f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
             f'test -d /sys/module/{PANEL}; '
             f'test -d /sys/bus/mipi-dsi/drivers/{PANEL}; '
             'test ! -e /sys/bus/platform/devices/14017000.dsi/driver; '
             'test ! -e /sys/class/drm/card0; '
             '/usr/local/bin/lynx-status --assert-ready >/dev/null; '
             'sample=$(cat /sys/bus/i2c/devices/7-0055/battery_snapshot); '
             'capacity=$(printf "%s\n" "$sample" | sed -n "s/^capacity_percent=//p"); '
             'temp=$(printf "%s\n" "$sample" | sed -n "s/^temperature_millidegrees_celsius=//p"); '
             'test "$capacity" -ge 70; test "$temp" -lt 35000; '
             'printf LYNX_DSI_BIND_READY')
        snapshot('before')
        step('bind_dsi',
             '/bin/busybox timeout 20 /bin/sh -c '
             "'printf 14017000.dsi > /sys/bus/platform/drivers/mtk-dsi/bind'",
             timeout=30)
        snapshot('after')
        report['state'] = 'dsi-bind-returned-and-host-healthy'
    except Exception as exc:
        report.update(state='failed-or-incomplete', error=str(exc))
        try:
            snapshot('after_failure')
        except Exception as snapshot_exc:
            report['post_failure_snapshot_error'] = str(snapshot_exc)
    report['finished_ns'] = time.time_ns()
    result = out / 'result.json'
    result.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(result)}))
    if report['state'] != 'dsi-bind-returned-and-host-healthy':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
