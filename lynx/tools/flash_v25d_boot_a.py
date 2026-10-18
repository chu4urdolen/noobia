"""Fixed V25d boot_a-only write with a live, read-only Fastboot preflight.

The command never reboots: USB must be unplugged before the first V25d boot.
An active general safety hold remains in force for all other Linux images.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parent.parent
IMAGE = ROOT / 'linux-port/artifacts/selfboot-health-v25d-offline/nord3-selfboot-health-untested.img'
STOCK = ROOT / 'linux-port/artifacts/stock-cph2493-August-eu-ota/boot.img'
FASTBOOT = ROOT / 'tools/platform-tools/fastboot'
SERIAL = '89BYAY5L4T9HFUOV'
IMAGE_SHA = '130d1cab9fdc48fc4ccafba75920d9bfb8a1a1c95f729ccae517ef1a790d7fb5'
STOCK_SHA = 'a67f03d7b826b834c23653b67eaa6efa971eb70ef8af19eee4d33fb5fc7fe995'
VARIANT = 'v25d'
EXCEPTION = ROOT / 'linux-port/docs/V25D-TRIAL-EXCEPTION.json'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def offline_check():
    checks = {}
    for name, path, expected in [(VARIANT, IMAGE, IMAGE_SHA), ('stock', STOCK, STOCK_SHA)]:
        if path.stat().st_size != 67108864 or digest(path) != expected:
            raise ValueError(name + ' image size or hash changed')
        checks[name] = {'file': str(path), 'sha256': expected, 'bytes': 67108864}
    build = json.loads((IMAGE.parent / 'build-result.json').read_text())
    if build['image_sha256'] != IMAGE_SHA or build['image_bytes'] != 67108864:
        raise ValueError(VARIANT + ' build receipt mismatch')
    integrity = json.loads((ROOT / 'downloads/august-eu-ota-integrity.json').read_text())
    signature = json.loads((ROOT / 'downloads/august-eu-payload-signature.json').read_text())
    if integrity.get('state') != 'verified' or signature.get('state') != 'verified' or not signature.get('full_payload_signature_valid'):
        raise ValueError('Matching stock OTA verification failed')
    baseline = json.loads((ROOT / 'logs/stock-boot-chain-1791640196780904534.json').read_text())
    if not baseline.get('all_four_writes_accepted'):
        raise ValueError('Prior stock boot-chain restore proof missing')
    if not any(item['partition'] == 'boot_a' and item['sha256'] == STOCK_SHA for item in baseline['images']):
        raise ValueError('Stock boot baseline mismatch')
    recorded = json.loads((ROOT / 'logs/fastboot-preflight-1791602958363822313.json').read_text())
    fastboot_sha = digest(FASTBOOT)
    if fastboot_sha != recorded['fastboot_sha256']:
        raise ValueError('Reviewed Fastboot binary changed')
    return checks, fastboot_sha


def save(path, report):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(report, indent=2) + '\n')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--flash', action='store_true')
    parser.add_argument('--observer-receipt', type=Path)
    args = parser.parse_args()
    checks, fastboot_sha = offline_check()
    report = {'state': 'offline-ready', 'created_ns': time.time_ns(),
              'images': checks, 'fastboot_sha256': fastboot_sha,
              'command': ['sudo', '-n', str(FASTBOOT), '-s', SERIAL, 'flash', 'boot_a', str(IMAGE)],
              'restore_command': ['sudo', '-n', str(FASTBOOT), '-s', SERIAL, 'flash', 'boot_a', str(STOCK)],
              'slot_b_preserved': True, 'other_partitions_preserved': True,
              'host_reboot_allowed': False, 'phone_contacted': False,
              'flash_performed': False, 'general_safety_hold_still_active': True}
    out = ROOT / 'logs' / (VARIANT + '-boot-a-trial-' + str(time.time_ns()) + '.json')
    save(out, report)
    if not args.flash:
        print(json.dumps({'state': 'offline-ready', 'result': str(out),
                          'restore_command': report['restore_command'],
                          'phone_contacted': False}))
        return
    if args.observer_receipt is None:
        raise ValueError('Fresh detached V25d observer receipt required')
    observer_path = args.observer_receipt.resolve(strict=True)
    if not observer_path.is_relative_to(ROOT / 'logs'):
        raise ValueError('Observer receipt escaped Lynx logs')
    observer = json.loads(observer_path.read_text())
    if (observer.get('state') != 'listening' or
            observer.get('image_sha256') != IMAGE_SHA or
            time.time_ns() - observer.get('heartbeat_ns', 0) > 15_000_000_000):
        raise ValueError('Observer is not fresh and ready for this image')
    hold = json.loads((ROOT / 'linux-port/docs/SAFETY-HOLD.json').read_text())
    exception = json.loads(EXCEPTION.read_text())
    if (not hold.get('active') or hold.get('linux_flash_allowed') is not False or
            exception.get('image_sha256') != IMAGE_SHA or
            exception.get('partition') != 'boot_a' or
            exception.get('requires_unplugged_boot') is not True or
            exception.get('single_supervised_trial') is not True):
        raise ValueError('Scoped safety review does not match current hold')
    report.update(state='read-only-preflight', phone_contacted=True,
                  observer_receipt=str(observer_path), exception_review=exception)
    save(out, report)
    preflight = subprocess.run(['sudo', '-n', 'python3', str(ROOT / 'tools/lynx_fastboot_preflight.py'), '--connect'],
                               capture_output=True, text=True, timeout=120)
    report['preflight_stdout'] = preflight.stdout
    report['preflight_stderr'] = preflight.stderr
    report['preflight_exit_code'] = preflight.returncode
    save(out, report)
    if preflight.returncode:
        raise ValueError('Fresh read-only Fastboot preflight failed; no write')
    fresh = json.loads(preflight.stdout)
    if int(fresh['values']['max-download-size'], 16) < 67108864:
        raise ValueError('Fastboot download limit smaller than V25d image')
    command = report['command']
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
                      'flash_exit_code': result.returncode,
                      'reboot_issued': False,
                      'restore_command': report['restore_command']}))
    if result.returncode:
        raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
