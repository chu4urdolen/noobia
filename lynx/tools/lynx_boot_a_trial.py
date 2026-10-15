"""Fixed, explicitly authorized boot_a trial and stock undo; no other writes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT / 'linux-port'
FASTBOOT = ROOT / 'tools/platform-tools/fastboot'
SERIAL = '89BYAY5L4T9HFUOV'
LINUX = PROJECT / 'artifacts/busybox-August/nord3-busybox-candidate.img'
STOCK = PROJECT / 'artifacts/stock-cph2493-August-eu-ota/boot.img'
EXPECTED = {LINUX: ('74bcda633bf85b2601629966e09e68e154863232f6493829b975bb277b3cf7f9', 21594112),
            STOCK: ('a67f03d7b826b834c23653b67eaa6efa971eb70ef8af19eee4d33fb5fc7fe995', 67108864)}


def main():
    parser = argparse.ArgumentParser()
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--flash-linux', action='store_true')
    actions.add_argument('--restore-stock', action='store_true')
    parser.add_argument('--reboot', action='store_true', help='Reboot only after a successful Linux image write')
    args = parser.parse_args()
    if args.reboot and not args.flash_linux:
        raise ValueError('Reboot is permitted only as part of the Linux trial')
    checks = []
    for path, (digest, size) in EXPECTED.items():
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != digest or path.stat().st_size != size:
            raise ValueError('Image hash or size changed: ' + str(path))
        checks.append({'file': str(path), 'sha256': actual, 'bytes': size})
    integrity = json.loads((ROOT / 'downloads/august-eu-ota-integrity.json').read_text())
    signature = json.loads((ROOT / 'downloads/august-eu-payload-signature.json').read_text())
    emulation = json.loads((PROJECT / 'artifacts/emulated-boot-August/result.json').read_text())
    if integrity['state'] != 'verified' or signature['state'] != 'verified' or not signature['full_payload_signature_valid']:
        raise ValueError('Stock OTA verification did not pass')
    if emulation['candidate_sha256'] != EXPECTED[LINUX][0] or not emulation['interactive_commands_executed']:
        raise ValueError('Exact candidate lacks successful interactive emulation')
    recorded = json.loads((ROOT / 'logs/fastboot-preflight-1791602958363822313.json').read_text())
    fastboot_hash = hashlib.sha256(FASTBOOT.read_bytes()).hexdigest()
    if fastboot_hash != recorded['fastboot_sha256']:
        raise ValueError('Fastboot binary changed since the reviewed preflight')
    trial_command = [str(FASTBOOT), '-s', SERIAL, 'flash', 'boot_a', str(LINUX)]
    restore_command = [str(FASTBOOT), '-s', SERIAL, 'flash', 'boot_a', str(STOCK)]
    report = {'mode': 'offline-readiness', 'images': checks, 'fastboot_sha256': fastboot_hash,
              'trial_command': trial_command, 'restore_command': restore_command,
              'authorized_partition': 'boot_a', 'slot_switch_allowed': False,
              'user_authorized_trial_and_fastboot_undo': True,
              'hardware_restoration_previously_tested': False,
              'phone_contacted': False, 'operations': []}
    output = ROOT / 'logs' / ('boot-a-trial-' + str(time.time_ns()) + '.json')

    def save():
        output.write_text(json.dumps(report, indent=2) + '\n')

    save()
    print('Stock boot image and exact restoration command verified.', flush=True)
    print('Report:', output, flush=True)
    if not (args.flash_linux or args.restore_stock):
        print(json.dumps(report, indent=2))
        return
    report.update(mode='restore-stock' if args.restore_stock else 'flash-linux', phone_contacted=True)
    save()
    preflight = subprocess.run(['python3', str(ROOT / 'tools/lynx_fastboot_preflight.py'), '--connect'],
                               capture_output=True, text=True, timeout=120)
    report['preflight_output'] = preflight.stdout + preflight.stderr
    save()
    if preflight.returncode != 0:
        raise ValueError('Fresh read-only preflight failed; no write issued')
    fresh = json.loads(preflight.stdout)
    if int(fresh['values']['max-download-size'], 16) < EXPECTED[STOCK][1]:
        raise ValueError('Fastboot limit does not cover prepared stock undo image')
    command = restore_command if args.restore_stock else trial_command
    report['operations'].append({'command': command, 'state': 'issued'})
    save()
    try:
        process = subprocess.run(command, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired as error:
        report['operations'][-1].update(state='timeout', output=str(error))
        save()
        raise
    text = process.stdout + process.stderr
    report['operations'][-1].update(state='returned', exit_code=process.returncode, output=text)
    save()
    print(text, flush=True)
    if process.returncode != 0:
        raise SystemExit(process.returncode)
    if args.reboot:
        command = [str(FASTBOOT), '-s', SERIAL, 'reboot']
        report['operations'].append({'command': command, 'state': 'issued'})
        save()
        process = subprocess.run(command, capture_output=True, text=True, timeout=15)
        report['operations'][-1].update(state='returned', exit_code=process.returncode,
                                        output=process.stdout + process.stderr)
        save()
        print(process.stdout + process.stderr, flush=True)
        if process.returncode != 0:
            raise SystemExit(process.returncode)


if __name__ == '__main__':
    main()
