"""Exercise V47's exact DHCP retry block with success and failure fixtures."""

import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / 'linux-port'
OUT = PORT / 'artifacts/wifi-dhcp-retry-v47-offline'
sys.path.insert(0, str(PORT))
from image_formats import read_boot_v4, read_newc
from ramdisk_codec import decompress


def main():
    image = (OUT / 'nord3-wifi-dhcp-retry-v47-untested.img').read_bytes()
    primary = read_newc(decompress(read_boot_v4(image)['ramdisk']))
    recipe = json.loads((PORT / 'known-good-v19/recipe.json').read_text())
    size = int(primary['etc/lynx/payload-bytes']['data'].strip())
    offset = recipe['payload_offset']
    members = read_newc(gzip.decompress(image[offset:offset + size]))
    script = members['etc/lynx/wifi-runtime.sh']['data']
    start = script.index(b'    dhcp_bound=0\n')
    end = script.index(b'    address=$($BB cat /run/lynx/address)', start)
    block = script[start:end]
    results = []
    with tempfile.TemporaryDirectory(prefix='lynx-v47-dhcp-') as directory:
        path = Path(directory)
        mock = path / 'mock-busybox'
        mock.write_text('''#!/bin/sh
case "$1" in
  udhcpc)
    count=$(cat "$COUNT_FILE")
    count=$((count+1))
    printf '%s\\n' "$count" > "$COUNT_FILE"
    [ "$count" -ge "$SUCCEED_AT" ]; exit $? ;;
  sleep) exit 0 ;;
  *) exit 99 ;;
esac
''')
        mock.chmod(0o700)
        for succeeds_at in (1, 2, 3, 4):
            counter = path / f'count-{succeeds_at}'
            counter.write_text('0\n')
            harness = (b'log() { :; }\nrun_retry() {\n'
                       b'BB="$MOCK_BB"; wifi_interface=wlan0\n' + block +
                       b'}\nrun_retry\n')
            result = subprocess.run(['/bin/sh'], input=harness,
                                    capture_output=True, timeout=5,
                                    env={'MOCK_BB': str(mock),
                                         'COUNT_FILE': str(counter),
                                         'SUCCEED_AT': str(succeeds_at)})
            expected_code = 0 if succeeds_at <= 3 else 144
            if result.returncode != expected_code or int(counter.read_text()) != min(succeeds_at, 3):
                raise ValueError(f'DHCP fixture {succeeds_at} failed: {result.stderr!r}')
            results.append({'succeeds_at': succeeds_at,
                            'attempts': int(counter.read_text()),
                            'exit_code': result.returncode})
    report = {'state': 'v47-dhcp-retry-fixtures-passed',
              'fixtures': results, 'phone_contacted': False}
    (OUT / 'dhcp-fixtures.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'state': report['state'],
                      'result': str(OUT / 'dhcp-fixtures.json')}))


if __name__ == '__main__':
    main()
