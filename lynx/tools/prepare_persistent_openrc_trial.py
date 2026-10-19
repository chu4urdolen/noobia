"""Audit V29, V19 and stock boot_a recovery commands without phone contact."""
import hashlib
import json
import os
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / 'linux-port'
V29_DIR = PORT / 'artifacts/persistent-openrc-v29-offline'
V29 = V29_DIR / 'nord3-persistent-openrc-untested.img'
V19 = PORT / 'artifacts/busybox-wifi-ssh-twostage-v19/nord3-busybox-candidate.img'
STOCK = PORT / 'artifacts/stock-cph2493-August-eu-ota/boot.img'
FASTBOOT = ROOT / 'tools/platform-tools/fastboot'
SERIAL = '89BYAY5L4T9HFUOV'
EXPECTED = {
    V29: '2483ba8d5ee43ef2ba692885682b9ebacc59fdb8216700eaad1eff7c531b3048',
    V19: '5ce2dbf8a7c132fa7e31f6be70aa76f83afe8c293e2cd5f02251a532486fd851',
    STOCK: 'a67f03d7b826b834c23653b67eaa6efa971eb70ef8af19eee4d33fb5fc7fe995',
}


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    os.umask(0o077)
    images = []
    for path, expected in EXPECTED.items():
        if path.stat().st_size != 67_108_864 or sha(path) != expected:
            raise ValueError('boot_a image differs: ' + str(path))
        images.append({'path': str(path), 'sha256': expected, 'bytes': 67_108_864})
    candidate = json.loads((V29_DIR / 'build-result.json').read_text())
    validation = json.loads((V29_DIR / 'validation.json').read_text())
    if (candidate.get('state') != 'offline-persistent-openrc-candidate-built' or
            candidate.get('image_sha256') != EXPECTED[V29] or
            validation.get('state') != 'offline-candidate-validation-passed' or
            validation.get('image_sha256') != EXPECTED[V29]):
        raise ValueError('V29 build/validation receipt differs')
    if V29.stat().st_mode & 0o777 != 0o600:
        raise ValueError('V29 private image mode differs')
    ota = json.loads((ROOT / 'downloads/august-eu-ota-integrity.json').read_text())
    signature = json.loads((ROOT / 'downloads/august-eu-payload-signature.json').read_text())
    if (ota.get('state') != 'verified' or signature.get('state') != 'verified' or
            not signature.get('full_payload_signature_valid')):
        raise ValueError('Matching stock OTA proof differs')
    baseline = json.loads((ROOT / 'logs/stock-boot-chain-1791640196780904534.json').read_text())
    if (not baseline.get('all_four_writes_accepted') or
            {item['partition']: item['sha256'] for item in baseline['images']}.get('boot_a') != EXPECTED[STOCK]):
        raise ValueError('Stock boot-chain restoration receipt differs')
    fastboot_record = json.loads((ROOT / 'logs/fastboot-preflight-1791602958363822313.json').read_text())
    if sha(FASTBOOT) != fastboot_record['fastboot_sha256']:
        raise ValueError('Pinned Fastboot tool differs')
    hold = json.loads((PORT / 'docs/SAFETY-HOLD.json').read_text())
    if not hold.get('active') or hold.get('linux_flash_allowed') is not False:
        raise ValueError('Thermal hold state changed; review before proceeding')
    out = ROOT / 'logs' / ('persistent-openrc-offline-readiness-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    prefix = [str(FASTBOOT), '-s', SERIAL]
    report = {
        'state': 'offline-recovery-ready-linux-flash-held',
        'created_ns': time.time_ns(), 'phone_contacted': False,
        'flash_performed': False, 'images': images,
        'fastboot_sha256': sha(FASTBOOT), 'serial': SERIAL,
        'fresh_fastboot_preflight': ['python3', str(ROOT / 'tools/lynx_fastboot_preflight.py'), '--connect'],
        'trial_command': prefix + ['flash', 'boot_a', str(V29)],
        'rollback_to_working_v19': prefix + ['flash', 'boot_a', str(V19)],
        'fallback_stock_boot_a': prefix + ['flash', 'boot_a', str(STOCK)],
        'partition_scope': ['boot_a'], 'slot_switch_allowed': False,
        'thermal_hold': hold,
        'limits': 'Commands audited offline only. No fresh Fastboot identity or recovery test yet; Linux flash remains held pending a scoped supervised exception and physical Fastboot USB.'
    }
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'], 'result': str(out / 'result.json')}))


if __name__ == '__main__':
    main()
