"""Filesystem fixture for the read-only cold-boot health gate."""
import hashlib
import json
import os
import platform
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'linux-port/autonomous-health-preflight.sh'
ARCHIVE = ROOT / 'linux-port/artifacts/autonomous-health-inputs/inputs.tar.gz'
OUT = ROOT / 'linux-port/artifacts'


def fixture(root):
    pack = root / 'pack'
    pack.mkdir()
    with tarfile.open(ARCHIVE, 'r:gz') as tar:
        for member in tar:
            if not member.isfile() or member.name.startswith('/') or '..' in Path(member.name).parts:
                raise ValueError('Unsafe input archive')
            destination = pack / member.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(tar.extractfile(member).read())
    sys = root / 'sys'
    dt = sys / 'firmware/devicetree/base'
    dt.mkdir(parents=True)
    (dt / 'fixture-property').write_text('stock fixture\n')
    digest = hashlib.sha256((dt / 'fixture-property').read_bytes()).hexdigest()
    (pack / 'review/DT-SHA256SUMS').write_text(digest + '  fixture-property\n')
    tag = dt / 'chosen/atag,devinfo'
    tag.parent.mkdir(parents=True)
    tag.write_bytes((210).to_bytes(4, 'little') + bytes(840))
    for name in ('clk_mt6983', 'reset_ti_syscon', 'oplus_project',
                 'oplusboot', 'buildvariant', 'mtk_boot_common'):
        (sys / 'module' / name).mkdir(parents=True)
    gauge = sys / 'bus/i2c/devices/7-0055'
    gauge.mkdir(parents=True)
    (gauge / 'name').write_text('bq27541-battery\n')
    (gauge / 'of_node/qcom,batt_bq28z610').parent.mkdir()
    (gauge / 'of_node/qcom,batt_bq28z610').touch()
    source = SOURCE.read_text().replace('BB=/bin/busybox', 'BB=/usr/bin/busybox')
    source = source.replace('SYS=/sys', 'SYS=' + str(sys))
    source = source.replace('EXPECTED_KERNEL=5.10.149-android12-9-o-g311738fbb5a8',
                            'EXPECTED_KERNEL=' + platform.uname().release)
    script = root / 'preflight.sh'
    script.write_text(source)
    return script, pack, sys, dt


def check(script, pack, expected, label):
    result = subprocess.run(['sh', str(script), '--check', str(pack)],
                            capture_output=True, text=True, timeout=5)
    passed = (result.returncode == 0) == expected
    if expected:
        passed &= 'LYNX_HEALTH_PREFLIGHT_PASS' in result.stdout
    else:
        passed &= 'LYNX_HEALTH_PREFLIGHT_REFUSED' in result.stderr
    if not passed:
        raise AssertionError(f'{label}: rc={result.returncode}; out={result.stdout}; err={result.stderr}')


def main():
    os.umask(0o077)
    with tempfile.TemporaryDirectory(prefix='lynx-health-gate-') as directory:
        root = Path(directory)
        script, pack, sys, dt = fixture(root)
        checks = []
        check(script, pack, True, 'reviewed fixture'); checks.append('reviewed fixture accepted')
        missing = sys / 'module/mtk_boot_common'
        missing.rmdir()
        check(script, pack, False, 'missing stock preloaded module'); checks.append('missing stock prerequisite refused')
        missing.mkdir()
        (dt / 'fixture-property').write_text('changed\n')
        check(script, pack, False, 'changed device tree'); checks.append('changed device tree refused')
        (dt / 'fixture-property').write_text('stock fixture\n')
        tag = dt / 'chosen/atag,devinfo'
        tag.write_bytes((211).to_bytes(4, 'little') + bytes(840))
        check(script, pack, False, 'truncated calibration'); checks.append('truncated calibration refused')
        tag.write_bytes((210).to_bytes(4, 'little') + bytes(840))
        driver = sys / 'bus/i2c/devices/7-0055/driver'
        driver.symlink_to('absent')
        check(script, pack, False, 'bound gauge'); checks.append('bound gauge refused')
        driver.unlink()
        (pack / 'modules/soc_temp_lvts.ko').unlink()
        check(script, pack, False, 'missing packed module'); checks.append('missing packed module refused')
    out = OUT / ('autonomous-health-preflight-check-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    report = {'passed': True, 'checks': checks, 'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
              'phone_contacted': False, 'flash_performed': False,
              'limits': 'Filesystem fixture and shell syntax only; real cold-boot sensor insertion remains untested.'}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': True, 'checks': len(checks), 'result': str(out / 'result.json')}))


if __name__ == '__main__':
    main()
