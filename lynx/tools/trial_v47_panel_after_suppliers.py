"""Single RAM-only NT37705 probe after all three known suppliers are bound."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
MODULE = ROOT / 'linux-port/artifacts/stock-cph2493-August-eu-ota/vendor-ramdisk-unpacked/lib/modules/oplus22823_tm_nt37705_fhd_dsi_cmd.ko'
MODULE_SHA = '498be900a01f21eba3116820d4fae965ee3796a953d30f66fb4aa72436334e98'
BOOT_ID = '00841cdb-6658-44d6-9f47-4770b047cad5'
INIT_SHA = 'ebc6bb746aaf710d915c47036f92ce0c4ed23a185dfb5349b90e654bab7ba4ae'
IP = '192.168.100.8'
STAGE = '/run/lynx/display-test/oplus22823_tm_nt37705_fhd_dsi_cmd.ko'


def main():
    data = MODULE.read_bytes()
    if hashlib.sha256(data).hexdigest() != MODULE_SHA:
        raise SystemExit('stock panel module hash mismatch')
    info = subprocess.run(['modinfo', '-F', 'vermagic', str(MODULE)],
                          capture_output=True, text=True, check=True).stdout.strip()
    if not info.startswith('5.10.149-android12-9-o-g311738fbb5a8 '):
        raise SystemExit('panel module ABI mismatch')
    os.umask(0o077)
    out = ROOT / 'logs' / f'v47-panel-after-suppliers-{time.time_ns()}'
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'boot_id': BOOT_ID,
              'module_sha256': MODULE_SHA, 'module_vermagic': info,
              'boot_partition_writes': False, 'steps': []}

    def step(label, command, payload=None, port=2222, timeout=25):
        argv = ssh_command(IP, command)
        argv[-2:-2] = ['-p', str(port)]
        run = subprocess.run(argv, input=payload, capture_output=True,
                             timeout=timeout)
        (out / f'{label}.stdout').write_bytes(run.stdout)
        (out / f'{label}.stderr').write_bytes(run.stderr)
        report['steps'].append({
            'name': label, 'exit_code': run.returncode,
            'stdout_sha256': hashlib.sha256(run.stdout).hexdigest(),
            'stderr_sha256': hashlib.sha256(run.stderr).hexdigest()})
        if run.returncode:
            raise RuntimeError(f'{label} failed; inspect saved streams')
        return run.stdout.decode(errors='replace')

    def snapshot(label):
        return step(label,
            'set -eu; '
            f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
            '/usr/local/bin/lynx-status --assert-ready; '
            'printf "DRM="; ls /sys/class/drm; '
            'printf "DSI_DRIVER="; '
            'readlink /sys/bus/platform/devices/14017000.dsi/driver || :; '
            'printf "PANEL_DRIVER="; '
            'ls /sys/bus/mipi-dsi/drivers/oplus22823_tm_nt37705_fhd_dsi_cmd 2>&1 | head -n 8 || :; '
            'printf "RECENT="; dmesg | grep -E '
            '"TM nt37705|oplus22823|mtk-dsi|mediatek-drm|DRM|Failed to add component" '
            '| tail -n 28 || :', timeout=35)

    try:
        step('rescue_identity',
             'set -eu; '
             f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
             f'test "$(sha256sum /init | cut -c1-64)" = "{INIT_SHA}"; '
             'printf LYNX_V47_RESCUE_VERIFIED', port=22)
        step('preflight',
             'set -eu; '
             f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
             'test "$(uname -r)" = 5.10.149-android12-9-o-g311738fbb5a8; '
             '/usr/local/bin/lynx-status --assert-ready >/dev/null; '
             'test -L /sys/bus/platform/devices/mt6373-pinctrl/driver; '
             'test -L /sys/bus/platform/devices/mt6373-auxadc/driver; '
             'test "$(ls /sys/class/iommu | wc -l)" -ge 1; '
             'test -L /sys/bus/platform/devices/1c00f000.dvfsrc/driver; '
             'cat /sys/class/regulator/regulator.*/name | grep -qx dvfsrc-vcore; '
             'grep -q "^cmdq_platform_mt6983 " /proc/modules; '
             'test ! -e /sys/module/oplus22823_tm_nt37705_fhd_dsi_cmd; '
             'test ! -L /sys/bus/platform/devices/14017000.dsi/driver; '
             'test ! -e /sys/class/drm/card0; '
             f'test ! -e {STAGE}; '
             'sample=$(cat /sys/bus/i2c/devices/7-0055/battery_snapshot); '
             'capacity=$(printf "%s\n" "$sample" | sed -n "s/^capacity_percent=//p"); '
             'temp=$(printf "%s\n" "$sample" | sed -n "s/^temperature_millidegrees_celsius=//p"); '
             'test "$capacity" -ge 70; test "$temp" -lt 35000; '
             'printf LYNX_PANEL_SUPPLIERS_READY')
        snapshot('before')
        step('stage', f'cat > {STAGE}', payload=data, timeout=35)
        step('stage_verify',
             f'test "$(sha256sum {STAGE} | cut -c1-64)" = "{MODULE_SHA}"')
        step('insmod', f'/bin/busybox timeout 15 /sbin/insmod {STAGE}', timeout=25)
        snapshot('after_insmod')
        if step('dsi_bound_probe',
                'if test -L /sys/bus/platform/devices/14017000.dsi/driver; '
                'then printf bound; else printf unbound; fi') == 'unbound':
            step('bind_dsi_once',
                 '/bin/busybox timeout 20 /bin/sh -c '
                 "'printf 14017000.dsi > /sys/bus/platform/drivers/mtk-dsi/bind'",
                 timeout=30)
        snapshot('after_bind')
        card = step('drm_card_probe',
                    'if test -e /sys/class/drm/card0; '
                    'then printf card0; else printf absent; fi')
        report['drm_card'] = card
        report['state'] = ('panel-bound-drm-card-present' if card == 'card0'
                           else 'panel-probe-returned-no-drm-card')
    except Exception as exc:
        report.update(state='failed-or-incomplete', error=str(exc))
        try:
            snapshot('after_failure')
        except Exception as capture_exc:
            report['capture_error'] = str(capture_exc)
    report['finished_ns'] = time.time_ns()
    result = out / 'result.json'
    result.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(result)}))
    if report['state'] != 'panel-bound-drm-card-present':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
