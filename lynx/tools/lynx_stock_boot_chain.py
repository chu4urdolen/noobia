"""Fixed matching stock slot-A boot-chain restoration; defaults to offline checks."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT / 'linux-port'
STOCK = PROJECT / 'artifacts/stock-cph2493-August-eu-ota'
FASTBOOT = ROOT / 'tools/platform-tools/fastboot'
SERIAL = '89BYAY5L4T9HFUOV'
EXPECTED_FASTBOOT = 'a686e2c7e8dc9cf4cba0cb8a2eef05f7b2bd682c925abd032fe203215d80b618'
IMAGES = (
    ('boot_a', 'boot.img', 67108864, 'a67f03d7b826b834c23653b67eaa6efa971eb70ef8af19eee4d33fb5fc7fe995'),
    ('vendor_boot_a', 'vendor_boot.img', 67108864, '373c40ce66c2cf37d86f104ddb8f5affc9ab9d2f499d61ac79244b569f172587'),
    ('dtbo_a', 'dtbo.img', 1077248, '44d947fdebee0f389295041f5af9a3509dc5dc8e1ec28c71d0b64370a8522e79'),
    ('vbmeta_a', 'vbmeta.img', 8192, 'ff7225b9242c460586e463ef9557eab463865546be20eb245c93b62883ea8484'),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--restore', action='store_true', help='Execute only the fixed four slot-A stock writes')
    parser.add_argument('--reboot-recovery', action='store_true', help='Request recovery only after every stock write and final checks pass')
    args = parser.parse_args()
    if args.reboot_recovery and not args.restore:
        raise ValueError('Recovery reboot requires a completed restoration')
    if hashlib.sha256(FASTBOOT.read_bytes()).hexdigest() != EXPECTED_FASTBOOT:
        raise ValueError('Fastboot binary changed')
    for name in ('august-eu-ota-integrity.json', 'august-eu-payload-signature.json'):
        if json.loads((ROOT / 'downloads' / name).read_text())['state'] != 'verified':
            raise ValueError('Full stock OTA verification report not verified')
    signature = json.loads((ROOT / 'downloads/august-eu-payload-signature.json').read_text())
    if not signature['full_payload_signature_valid']:
        raise ValueError('Whole payload signature evidence missing')
    audit = json.loads((PROJECT / 'docs/august-stock-avb-audit.json').read_text())
    checks = []
    for partition, name, size, expected in IMAGES:
        path = STOCK / name
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected or path.stat().st_size != size:
            raise ValueError('Stock file changed: ' + name)
        if audit['images'][name]['sha256'] != expected:
            raise ValueError('AVB audit does not describe selected stock file')
        if name in ('boot.img', 'vbmeta.img'):
            item = audit['images'][name]
            if not item['signature_valid_against_embedded_key'] or item['flags'] != 0:
                raise ValueError('Unexpected stock verification signature or flags')
        checks.append({'partition': partition, 'file': str(path), 'sha256': actual, 'bytes': size})
    for descriptor in audit['descriptor_checks']:
        if descriptor.get('valid') is False or descriptor.get('embedded_child_key_matches') is False:
            raise ValueError('Stock AVB reference chain inconsistent')
    report = {'mode': 'offline-readiness', 'images': checks, 'serial': SERIAL,
              'fastboot_sha256': EXPECTED_FASTBOOT, 'phone_contacted': False,
              'authorized_scope': 'User expanded authorization to judged-safe flashing to recover Lynx and enable native Linux',
              'partition_allowlist': [item[0] for item in IMAGES], 'slot_switch_allowed': False,
              'verification_disable_flags_used': False, 'authentication_bypass_used': False,
              'original_companion_partition_readbacks_available': False, 'recovery_boot_proven': False,
              'commands': [[str(FASTBOOT), '-s', SERIAL, 'flash', partition, str(STOCK / name)]
                           for partition, name, _, _ in IMAGES], 'operations': [],
              'limits': ['Stock package LK build matches observed bootloader; installed companion images were not read back.',
                         'Embedded OTA/signature verification is not independent manufacturer-key trust.',
                         'Phone rollback indexes remain unknown.',
                         'This restores kernel/recovery foundations, not Android system/vendor/userdata.']}
    output = ROOT / 'logs' / ('stock-boot-chain-' + str(time.time_ns()) + '.json')

    def save():
        output.write_text(json.dumps(report, indent=2) + '\n')

    def preflight():
        result = subprocess.run(['python3', str(ROOT / 'tools/lynx_fastboot_preflight.py'), '--connect'],
                                capture_output=True, text=True, timeout=120)
        report.setdefault('preflights', []).append({'exit_code': result.returncode, 'output': result.stdout + result.stderr})
        save()
        if result.returncode:
            raise ValueError('Fresh preflight failed; sequence stopped')
        values = json.loads(result.stdout)['values']
        for partition, _, size, _ in IMAGES:
            if int(values['partition-size:' + partition], 16) < size:
                raise ValueError('Stock image exceeds partition size')
        if int(values['max-download-size'], 16) < 67108864:
            raise ValueError('Full stock image exceeds download size')

    save()
    print('Four stock images verified. Receipt:', output, flush=True)
    if not args.restore:
        print(json.dumps(report, indent=2))
        return
    report.update(mode='restore-stock-boot-chain', phone_contacted=True)
    save()
    preflight()
    for command in report['commands']:
        operation = {'command': command, 'state': 'issued'}
        report['operations'].append(operation)
        save()
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            operation.update(state='timeout')
            save()
            raise
        operation.update(state='returned', exit_code=result.returncode, output=result.stdout + result.stderr)
        save()
        print(operation['output'], flush=True)
        if result.returncode:
            raise SystemExit(result.returncode)
    preflight()
    report['all_four_writes_accepted'] = True
    save()
    if args.reboot_recovery:
        command = [str(FASTBOOT), '-s', SERIAL, 'reboot', 'recovery']
        operation = {'command': command, 'state': 'issued'}
        report['operations'].append(operation)
        save()
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=15)
        except subprocess.TimeoutExpired:
            operation.update(state='timeout')
            save()
            raise
        operation.update(state='returned', exit_code=result.returncode, output=result.stdout + result.stderr)
        save()
        print(operation['output'], flush=True)
        if result.returncode:
            raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
