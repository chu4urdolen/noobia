"""Fixed read-only Fastboot preflight for Lynx; default mode contacts no device."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parent.parent
FASTBOOT = ROOT / 'tools/platform-tools/fastboot'
SERIAL = '89BYAY5L4T9HFUOV'
VARIABLES = ('product', 'unlocked', 'secure', 'current-slot', 'version-bootloader',
             'slot-successful:a', 'slot-unbootable:a', 'slot-retry-count:a',
             'partition-size:boot_a', 'partition-size:vendor_boot_a',
             'partition-size:dtbo_a', 'partition-size:vbmeta_a', 'max-download-size')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--connect', action='store_true', help='Run only the fixed getvar queries against Lynx')
    args = parser.parse_args()
    commands = [[str(FASTBOOT), '-s', SERIAL, 'getvar', variable] for variable in VARIABLES]
    if not args.connect:
        print(json.dumps({'mode': 'offline-plan', 'serial': SERIAL, 'commands': commands,
                          'phone_contacted': False, 'writes_allowed': False}, indent=2))
        return
    report = {'serial': SERIAL, 'mode': 'read-only-getvar', 'phone_contacted': True,
              'fastboot_sha256': hashlib.sha256(FASTBOOT.read_bytes()).hexdigest(),
              'queries': [], 'values': {}, 'writes_allowed': False, 'flash_eligible': False}
    output = ROOT / 'logs' / ('fastboot-preflight-' + str(time.time_ns()) + '.json')
    for variable, command in zip(VARIABLES, commands):
        try:
            process = subprocess.run(command, capture_output=True, text=True, timeout=8)
            text = process.stdout + process.stderr
            matches = re.findall(r'(?:^|\n)(?:\(bootloader\)[ \t]*)?' + re.escape(variable) + r':[ \t]*([^\r\n]*)', text)
            value = matches[0].strip() if len(matches) == 1 else None
            report['queries'].append({'variable': variable, 'exit_code': process.returncode, 'output': text})
            report['values'][variable] = value
            if process.returncode != 0:
                report['error'] = 'Query failed; sequence stopped without fallback'
                break
        except subprocess.TimeoutExpired:
            report['error'] = 'Query timed out; sequence stopped without fallback'
            break
        if variable == 'product' and value != 'k6983v1_64':
            report['error'] = 'Unexpected product; no further device queries'
            break
    values = report['values']
    expected = {'product': 'k6983v1_64', 'unlocked': 'yes', 'current-slot': 'a',
                'version-bootloader': 'k6983v1_64_45ca337_202308100614'}
    report['identity_and_slot_match'] = all(values.get(key) == value for key, value in expected.items())
    expected_sizes = {'partition-size:boot_a': 67108864, 'partition-size:vendor_boot_a': 67108864,
                      'partition-size:dtbo_a': 8388608, 'partition-size:vbmeta_a': 8388608}
    try:
        report['partition_layout_match'] = all(int(values.get(key) or '', 16) == size for key, size in expected_sizes.items())
        report['download_limit_sufficient'] = int(values.get('max-download-size') or '', 16) >= 21594112
    except ValueError:
        report['partition_layout_match'] = False
        report['download_limit_sufficient'] = False
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'report': str(output), 'values': values,
                      'identity_and_slot_match': report['identity_and_slot_match'],
                      'partition_layout_match': report['partition_layout_match'],
                      'download_limit_sufficient': report['download_limit_sufficient'],
                      'error': report.get('error'), 'writes_allowed': False}, indent=2))
    if report.get('error') or not report['identity_and_slot_match'] or not report['partition_layout_match'] or not report['download_limit_sufficient']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
