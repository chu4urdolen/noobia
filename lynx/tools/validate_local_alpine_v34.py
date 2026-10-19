"""Independently validate the unflashed V34 local Alpine boot image."""
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / 'linux-port'
OUT = PORT / 'artifacts/local-persistent-alpine-v34-offline'
PARENT = PORT / 'artifacts/persistent-openrc-v33-offline/nord3-persistent-openrc-v33-untested.img'
STOCK = PORT / 'artifacts/stock-cph2493-August-eu-ota'
MODEL = ROOT / 'tools/avb-host/avb-boot-model'
sys.path.insert(0, str(PORT))
from image_formats import read_boot_v4, read_newc
from ramdisk_codec import decompress


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run(argv, timeout=20):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise ValueError('Validation command failed: ' + ' '.join(argv) + ' ' + result.stderr[-300:])
    return result.stdout


def main():
    build = json.loads((OUT / 'build-result.json').read_text())
    image = OUT / 'nord3-local-persistent-alpine-v34-untested.img'
    data, parent, stock = image.read_bytes(), PARENT.read_bytes(), (STOCK / 'boot.img').read_bytes()
    if (build['state'] != 'offline-autonomous-alpine-candidate-built' or
            sha(data) != build['image_sha256'] or
            sha(parent) != build['parent_v33_sha256'] or
            sha(stock) != 'a67f03d7b826b834c23653b67eaa6efa971eb70ef8af19eee4d33fb5fc7fe995'):
        raise ValueError('Image, V33 parent, or stock provenance differs')
    boot, base_boot, stock_boot = map(read_boot_v4, (data, parent, stock))
    if boot['kernel'] != base_boot['kernel'] or boot['kernel'] != stock_boot['kernel']:
        raise ValueError('Stock kernel differs')
    entries = read_newc(decompress(boot['ramdisk']))
    old = read_newc(decompress(base_boot['ramdisk']))
    if (set(entries) != set(old) or
            any(entries[name] != old[name] for name in old
                if name not in ('init', 'etc/lynx/payload-bytes', 'etc/lynx/payload-sha256'))):
        raise ValueError('Primary member scope differs')
    init = entries['init']['data']
    marker = b'. /etc/lynx/wifi-runtime.sh || stop\nlynx_wifi_supervise || stop\n'
    tail = (PORT / 'lynx-v34-init-tail.sh').read_bytes()
    if old['init']['data'].count(marker) != 1 or init != old['init']['data'].split(marker)[0] + tail:
        raise ValueError('V34 init tail not exact')
    run(['busybox', 'sh', '-n', str(OUT / 'init-source')])
    recipe = json.loads((PORT / 'known-good-v19/recipe.json').read_text())
    offset = recipe['payload_offset']
    length = int(entries['etc/lynx/payload-bytes']['data'])
    payload = data[offset:offset + length]
    if (sha(payload) != build['payload_sha256'] or
            sha(payload) != entries['etc/lynx/payload-sha256']['data'].strip().decode()):
        raise ValueError('Payload hash metadata differs')
    supplement = read_newc(gzip.decompress(payload))
    expected = {
        'etc/lynx/wifi-local-supervise.sh': PORT / 'lynx-wifi-local-supervise-v34.sh',
        'etc/lynx/autonomous-health-local-handoff.sh': PORT / 'autonomous-health-local-handoff.sh',
        'etc/lynx/persistent-openrc-handoff.sh': PORT / 'persistent-openrc-handoff-v34.sh',
        'usr/libexec/lynx/autonomous-health-start.sh': PORT / 'autonomous-health-start-v31.sh',
        'usr/libexec/lynx/autonomous-health-preflight.sh': PORT / 'autonomous-health-preflight.sh',
    }
    for member, source in expected.items():
        if supplement[member]['data'] != source.read_bytes():
            raise ValueError('V34 supplement source differs: ' + member)
        run(['busybox', 'sh', '-n', str(source)])
    archive = supplement['usr/share/lynx/health-inputs.tar.gz']['data']
    if (sha(archive) != build['health_inputs_sha256'] or
            supplement['usr/share/lynx/health-inputs.sha256']['data'].strip().decode() != sha(archive)):
        raise ValueError('Reviewed health archive hash differs')
    # The local path must not quietly depend on the host's one-boot marker.
    if (b'LYNX_OPENRC_AUTHORITY=local' not in supplement[
            'etc/lynx/persistent-openrc-handoff.sh']['data'] or
            b'lynx_wifi_local_supervise ||' not in init or
            b'lynx_autonomous_health_local_handoff ||' not in init or
            b'exec </dev/null 1>>/run/lynx/openrc-pid1-stdout.log' not in init):
        raise ValueError('Local Wi-Fi/health/stdio handoff chain missing')
    # The fixture checks V31's clean cooling retry and partial-state refusal.
    fixture = run(['python3', str(ROOT / 'tools/test_autonomous_health_start_v31_fixture.py'),
                   '--mode', 'local', '--cooling-behavior', 'transient'], timeout=30)
    if '"passed": true' not in fixture.lower():
        raise ValueError('V31 local fixture did not report pass')
    reference = json.loads((PORT / 'docs/avb-boot-model-results.json').read_text())
    if sha(MODEL.read_bytes()) != reference['binary_sha256']:
        raise ValueError('Pinned AOSP AVB model differs')
    avb_cases = []
    for unlocked in (1, 0):
        avb_cases.append(json.loads(run([str(MODEL), str(STOCK), str(image), '0', str(unlocked)])))
    if not (avb_cases[0]['slot_data_returned'] and avb_cases[0]['boot_partitions_loaded'] == 1 and
            not avb_cases[1]['slot_data_returned'] and avb_cases[1]['boot_partitions_loaded'] == 0):
        raise ValueError('AOSP AVB model behavior differs')
    result = {'state': 'offline-v34-validation-passed', 'created_ns': time.time_ns(),
              'image_sha256': build['image_sha256'], 'stock_kernel_sha256': sha(stock_boot['kernel']),
              'busybox_syntax_passed': True, 'health_local_fixture_passed': True,
              'avb_cases': avb_cases, 'phone_contacted': False, 'flash_performed': False,
              'limit': 'AOSP AVB model is not OnePlus LK; autonomous hardware boot remains untested.'}
    (OUT / 'validation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'state': result['state'], 'result': str(OUT / 'validation.json')}))


if __name__ == '__main__':
    main()
