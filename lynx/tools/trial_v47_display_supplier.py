"""Guarded RAM-only trial of one exact stock display prerequisite."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
MODULE_DIR = ROOT / 'linux-port/artifacts/stock-cph2493-August-eu-ota/vendor-ramdisk-unpacked/lib/modules'
IP = '192.168.100.8'
BOOT_ID = '00841cdb-6658-44d6-9f47-4770b047cad5'
INIT_SHA = 'ebc6bb746aaf710d915c47036f92ce0c4ed23a185dfb5349b90e654bab7ba4ae'
SUPPLIERS = {
    'pinctrl-mt6373': {
        'sha': 'c48f4fe779e3dd084d329a441f51d381df9b004c3d566520233215a1b92c6694',
        'check': 'test -L /sys/bus/platform/devices/mt6373-pinctrl/driver',
        'deps': ('pinctrl_mtk_v2',),
    },
    'mtk-spmi-pmic-adc': {
        'sha': '66a3e5426b200acf783413a09561e584cb89fd20244d9d8568d399431468e01c',
        'check': 'test -L /sys/bus/platform/devices/mt6373-auxadc/driver',
        'deps': (),
    },
    'mtk_iommu': {
        'sha': 'f2f2d31ec2dcb769311dfab3621622a7deff7ba83d14c2f5137d94f38c44b332',
        'check': 'test "$(ls /sys/class/iommu | wc -l)" -ge 1',
        'deps': ('iommu_secure', 'iommu_debug', 'mtk_smi_dbg'),
    },
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('module', choices=SUPPLIERS)
    args = parser.parse_args()
    name = args.module
    config = SUPPLIERS[name]
    data = (MODULE_DIR / (name + '.ko')).read_bytes()
    if hashlib.sha256(data).hexdigest() != config['sha']:
        raise SystemExit('stock module hash mismatch')
    info = subprocess.run(['modinfo', '-F', 'vermagic',
                           str(MODULE_DIR / (name + '.ko'))],
                          capture_output=True, text=True, check=True).stdout.strip()
    if not info.startswith('5.10.149-android12-9-o-g311738fbb5a8 '):
        raise SystemExit('stock module ABI mismatch')
    modname = name.replace('-', '_')
    staged = '/run/lynx/display-test/' + name + '.ko'
    os.umask(0o077)
    out = ROOT / 'logs' / f'v47-display-supplier-{name}-{time.time_ns()}'
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'boot_id': BOOT_ID, 'module': name,
              'module_sha256': config['sha'], 'vermagic': info,
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

    try:
        step('rescue_identity',
             'set -eu; '
             f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
             f'test "$(sha256sum /init | cut -c1-64)" = "{INIT_SHA}"; '
             'printf LYNX_V47_RESCUE_VERIFIED', port=22)
        deps = ' '.join(f'grep -q "^{dep} " /proc/modules; ' for dep in config['deps'])
        preflight = (
             'set -eu; '
             f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
             'test "$(uname -r)" = 5.10.149-android12-9-o-g311738fbb5a8; '
             '/usr/local/bin/lynx-status --assert-ready >/dev/null; '
             'test ! -e /sys/module/oplus22823_tm_nt37705_fhd_dsi_cmd; '
             f'test ! -e /sys/module/{modname}; '
             f'test ! -e {staged}; ')
        preflight += deps + (
             'sample=$(cat /sys/bus/i2c/devices/7-0055/battery_snapshot); '
             'capacity=$(printf "%s\n" "$sample" | sed -n "s/^capacity_percent=//p"); '
             'temp=$(printf "%s\n" "$sample" | sed -n "s/^temperature_millidegrees_celsius=//p"); '
             'test "$capacity" -ge 70; test "$temp" -lt 35000; '
             'printf LYNX_DISPLAY_SUPPLIER_READY')
        step('preflight', preflight)
        step('before',
             '/usr/local/bin/lynx-status --assert-ready; '
             f'printf "TARGET="; ls /sys/module/{modname} 2>&1 | head -n 2 || :')
        step('stage', 'mkdir -p /run/lynx/display-test; '
             f'cat > {staged}', payload=data)
        step('stage_verify',
             f'test "$(sha256sum {staged} | cut -c1-64)" = "{config["sha"]}"')
        step('insmod', f'/bin/busybox timeout 15 /sbin/insmod {staged}', timeout=25)
        after = (
             'set -eu; '
             f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{BOOT_ID}"; '
             f'test -d /sys/module/{modname}; ')
        after += config['check'] + '; ' + (
             '/usr/local/bin/lynx-status --assert-ready; '
             'printf "IOMMU="; ls /sys/class/iommu; '
             'printf "IIO="; ls /sys/bus/iio/devices; '
             'printf "DISPLAY="; ls /sys/class/drm; '
             'printf "RECENT="; dmesg | grep -E '
             '"mt6373-pinctrl|mt6373-auxadc|mtk-iommu|iommu|pmic_adc_probe" '
             '| tail -n 20 || :')
        step('after', after, timeout=35)
        report['state'] = 'supplier-loaded-and-host-healthy'
    except Exception as exc:
        report.update(state='failed-or-incomplete', error=str(exc))
        try:
            step('after_failure',
                 f'cat /proc/sys/kernel/random/boot_id; '
                 '/usr/local/bin/lynx-status; '
                 f'ls /sys/module/{modname} 2>&1 | head -n 2 || :', timeout=15)
        except Exception as capture_exc:
            report['capture_error'] = str(capture_exc)
    report['finished_ns'] = time.time_ns()
    result = out / 'result.json'
    result.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(result)}))
    if report['state'] != 'supplier-loaded-and-host-healthy':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
