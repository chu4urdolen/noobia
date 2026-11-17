"""Load the stock MT6373 ADC that supplies the NT37705 panel NTC channel."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
MODULE = ROOT / 'linux-port/artifacts/stock-cph2493-August-eu-ota/vendor-ramdisk-unpacked/lib/modules/mtk-spmi-pmic-adc.ko'
MODULE_SHA = '66a3e5426b200acf783413a09561e584cb89fd20244d9d8568d399431468e01c'
INIT_SHA = 'ebc6bb746aaf710d915c47036f92ce0c4ed23a185dfb5349b90e654bab7ba4ae'
BOOT_ID = '9054078d-aafa-4abf-9600-5c70f8234360'
IP = '192.168.100.8'
STAGE = '/run/lynx/display-test/mtk-spmi-pmic-adc.ko'


def main():
    data = MODULE.read_bytes()
    if hashlib.sha256(data).hexdigest() != MODULE_SHA:
        raise SystemExit('stock ADC module hash mismatch')
    info = subprocess.run(['modinfo', '-F', 'vermagic', str(MODULE)],
                          capture_output=True, text=True, check=True).stdout.strip()
    if not info.startswith('5.10.149-android12-9-o-g311738fbb5a8 '):
        raise SystemExit('stock ADC module ABI mismatch')
    os.umask(0o077)
    out = ROOT / 'logs' / f'v47-runtime-panel-adc-{time.time_ns()}'
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'boot_id': BOOT_ID,
              'module_sha256': MODULE_SHA, 'module_vermagic': info,
              'boot_partition_writes': False, 'steps': []}

    def step(name, command, payload=None, port=2222, timeout=25):
        argv = ssh_command(IP, command)
        argv[-2:-2] = ['-p', str(port)]
        run = subprocess.run(argv, input=payload, capture_output=True,
                             timeout=timeout)
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
            'printf "IIO="; ls /sys/bus/iio/devices; '
            'printf "ADC_DRIVER="; '
            'readlink /sys/bus/platform/devices/mt6373-auxadc/driver || :; '
            'printf "PANEL_DRIVER="; '
            'ls /sys/bus/mipi-dsi/drivers/oplus22823_tm_nt37705_fhd_dsi_cmd; '
            'printf "DRM="; ls /sys/class/drm; '
            'printf "ADC_DISPLAY_LOG="; '
            'dmesg | grep -E "mt6373-auxadc|pmic_adc_probe|TM nt37705|panel channel|mtk-dsi|drm_dev" '
            '| tail -n 26 || :', timeout=35)

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
             'test ! -e /sys/module/mtk_spmi_pmic_adc; '
             f'test ! -e {STAGE}; '
             'test -d /sys/bus/platform/devices/mt6373-auxadc; '
             'test -d /sys/module/oplus22823_tm_nt37705_fhd_dsi_cmd; '
             'test ! -e /sys/class/drm/card0; '
             'sample=$(cat /sys/bus/i2c/devices/7-0055/battery_snapshot); '
             'capacity=$(printf "%s\n" "$sample" | sed -n "s/^capacity_percent=//p"); '
             'temp=$(printf "%s\n" "$sample" | sed -n "s/^temperature_millidegrees_celsius=//p"); '
             'test "$capacity" -ge 70; test "$temp" -lt 35000; '
             'printf LYNX_ADC_TRIAL_READY')
        snapshot('before')
        step('stage', f'cat > {STAGE}', payload=data, timeout=25)
        step('stage_verify',
             f'test "$(sha256sum {STAGE} | cut -c1-64)" = "{MODULE_SHA}"; '
             'printf LYNX_ADC_MODULE_VERIFIED')
        step('insmod', f'/bin/busybox timeout 15 /sbin/insmod {STAGE}', timeout=25)
        snapshot('after')
        report['state'] = 'adc-module-loaded-and-host-healthy'
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
    if report['state'] != 'adc-module-loaded-and-host-healthy':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
