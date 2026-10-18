"""Restore the proven V19 BusyBox boot_a image after a failed new trial.

Requires the matching stock undo, fresh Fastboot identity, and a bounded V19
network collector. Never reboots or touches any partition other than boot_a.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parent.parent
IMAGE = ROOT / 'linux-port/artifacts/busybox-wifi-ssh-twostage-v19/nord3-busybox-candidate.img'
STOCK = ROOT / 'linux-port/artifacts/stock-cph2493-August-eu-ota/boot.img'
FASTBOOT = ROOT / 'tools/platform-tools/fastboot'
SERIAL = '89BYAY5L4T9HFUOV'
IMAGE_SHA = '5ce2dbf8a7c132fa7e31f6be70aa76f83afe8c293e2cd5f02251a532486fd851'
STOCK_SHA = 'a67f03d7b826b834c23653b67eaa6efa971eb70ef8af19eee4d33fb5fc7fe995'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def save(path, report):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(report, indent=2) + '\n')
    tmp.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--flash', action='store_true')
    parser.add_argument('--collector-receipt', type=Path)
    args = parser.parse_args()
    for path, expected in [(IMAGE, IMAGE_SHA), (STOCK, STOCK_SHA)]:
        if path.stat().st_size != 67108864 or digest(path) != expected:
            raise ValueError('Image size/hash mismatch: ' + str(path))
    manifest = json.loads((IMAGE.parent / 'build-validation.json').read_text())
    if manifest.get('candidate_sha256') != IMAGE_SHA:
        raise ValueError('V19 build validation does not match image')
    signature = json.loads((ROOT / 'downloads/august-eu-payload-signature.json').read_text())
    integrity = json.loads((ROOT / 'downloads/august-eu-ota-integrity.json').read_text())
    if not signature.get('full_payload_signature_valid') or signature.get('state') != 'verified' or integrity.get('state') != 'verified':
        raise ValueError('Matching stock rollback signature/integrity missing')
    baseline = json.loads((ROOT / 'logs/stock-boot-chain-1791640196780904534.json').read_text())
    if not baseline.get('all_four_writes_accepted') or not any(
            item['partition'] == 'boot_a' and item['sha256'] == STOCK_SHA
            for item in baseline['images']):
        raise ValueError('Prior stock rollback proof missing')
    recorded = json.loads((ROOT / 'logs/fastboot-preflight-1791602958363822313.json').read_text())
    if digest(FASTBOOT) != recorded['fastboot_sha256']:
        raise ValueError('Reviewed Fastboot binary changed')
    command = ['sudo', '-n', str(FASTBOOT), '-s', SERIAL, 'flash', 'boot_a', str(IMAGE)]
    restore = ['sudo', '-n', str(FASTBOOT), '-s', SERIAL, 'flash', 'boot_a', str(STOCK)]
    out = ROOT / 'logs' / ('v19-rescue-boot-a-' + str(time.time_ns()) + '.json')
    report = {'state': 'offline-ready', 'created_ns': time.time_ns(),
              'v19_sha256': IMAGE_SHA, 'stock_sha256': STOCK_SHA,
              'command': command, 'stock_restore_command': restore,
              'partition': 'boot_a', 'automatic_reboot': False,
              'phone_contacted': False, 'flash_performed': False,
              'general_safety_hold_still_active': True}
    save(out, report)
    if not args.flash:
        print(json.dumps({'state': 'offline-ready', 'result': str(out),
                          'phone_contacted': False, 'stock_restore_command': restore}))
        return
    if args.collector_receipt is None:
        raise ValueError('Fresh V19 pinned collector required')
    receipt = args.collector_receipt.resolve(strict=True)
    if not receipt.is_relative_to(ROOT / 'logs'):
        raise ValueError('Collector receipt escaped Lynx logs')
    collector = json.loads(receipt.read_text())
    if (collector.get('state') != 'listening' or
            collector.get('session_token') != manifest['session_token'] or
            time.time_ns() - collector.get('heartbeat_ns', 0) > 15_000_000_000):
        raise ValueError('V19 collector not fresh/ready')
    exception = json.loads((ROOT / 'linux-port/docs/V19-RESCUE-EXCEPTION.json').read_text())
    hold = json.loads((ROOT / 'linux-port/docs/SAFETY-HOLD.json').read_text())
    if (not hold.get('active') or hold.get('linux_flash_allowed') is not False or
            exception.get('image_sha256') != IMAGE_SHA or
            exception.get('partition') != 'boot_a' or
            exception.get('single_supervised_rescue') is not True):
        raise ValueError('Scoped V19 rescue review does not match active hold')
    report.update(state='read-only-preflight', phone_contacted=True,
                  collector_receipt=str(receipt), exception_review=exception)
    save(out, report)
    preflight = subprocess.run(['sudo', '-n', 'python3', str(ROOT / 'tools/lynx_fastboot_preflight.py'), '--connect'],
                               capture_output=True, text=True, timeout=120)
    report.update(preflight_stdout=preflight.stdout, preflight_stderr=preflight.stderr,
                  preflight_exit_code=preflight.returncode)
    save(out, report)
    if preflight.returncode:
        raise ValueError('Fresh Fastboot preflight failed; no write')
    values = json.loads(preflight.stdout)['values']
    if int(values['max-download-size'], 16) < 67108864:
        raise ValueError('Fastboot download limit smaller than V19 image')
    report.update(state='write-issued', write_started_ns=time.time_ns())
    save(out, report)
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired as error:
        report.update(state='write-timeout-unknown', error=str(error), finished_ns=time.time_ns())
        save(out, report)
        raise
    report.update(state='written-await-unplugged-boot' if result.returncode == 0 else 'write-failed',
                  finished_ns=time.time_ns(), flash_exit_code=result.returncode,
                  flash_stdout=result.stdout, flash_stderr=result.stderr,
                  flash_performed=result.returncode == 0)
    save(out, report)
    print(json.dumps({'state': report['state'], 'result': str(out),
                      'flash_exit_code': result.returncode, 'reboot_issued': False}))
    if result.returncode:
        raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
