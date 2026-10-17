"""Exercise the exact V21 init tail's failure paths without contacting Lynx."""
import gzip
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'linux-port'))
from image_formats import read_boot_v4, read_newc
from ramdisk_codec import decompress

OUT = ROOT / 'linux-port/artifacts' / ('openrc-failclosed-check-' + str(time.time_ns()))
CANDIDATE = ROOT / 'linux-port/artifacts/openrc-gated-v21-fastboot-timeout'


def main():
    OUT.mkdir(mode=0o700)
    manifest = json.loads((CANDIDATE / 'build-result.json').read_text())
    image = (CANDIDATE / 'nord3-openrc-gated-candidate.img').read_bytes()
    assert hashlib.sha256(image).hexdigest() == manifest['candidate_sha256']
    init = read_newc(decompress(read_boot_v4(image)['ramdisk']))['init']['data']
    assert hashlib.sha256(init).hexdigest() == manifest['init_sha256']
    marker = b'lynx_wifi_supervise || stop\n'
    assert init.count(marker) == 1
    tail = init[init.index(marker):]
    assert tail.count(b'/bin/boot-proof-reboot') == 2
    assert tail.index(b'lynx_openrc_handoff') < tail.index(b"log 'OPENRC_HANDOFF_FAILED")
    supplement = read_newc(gzip.decompress((CANDIDATE / 'supplement.cpio.gz').read_bytes()))
    handoff = supplement['etc/lynx/openrc-handoff.sh']['data']
    assert hashlib.sha256(handoff).hexdigest() == manifest['handoff_script_sha256']
    assert b'wait_deadline=$((wait_start+180))' in handoff
    assert b'BUSYBOX_RETAINED' not in handoff

    cases = {}
    for name, wifi_status, handoff_status, source_ok, expected_requests in (
        ('wifi-failure-stops-after-original-reset', 1, 0, True, 0),
        ('gate-failure-requests-fastboot-once', 0, 1, True, 1),
        ('script-load-failure-requests-fastboot-once', 0, 0, False, 1),
        ('unexpected-handoff-return-requests-fastboot-once', 0, 0, True, 1),
    ):
        mock_tail = tail.replace(b'. /etc/lynx/openrc-handoff.sh', b'true' if source_ok else b'false')
        mock_tail = mock_tail.replace(b'/bin/boot-proof-reboot', b'fake_fastboot_request')
        prelude = (f'lynx_wifi_supervise() {{ return {wifi_status}; }}\n'
                   f'lynx_openrc_handoff() {{ return {handoff_status}; }}\n'
                   'fake_fastboot_request() { echo BOOTLOADER_REQUEST; }\n'
                   'log() { :; }\n'
                   'stop() { echo INIT_STOPPED; exit 0; }\n').encode()
        result = subprocess.run(['/bin/sh'], input=prelude + mock_tail,
                                capture_output=True, timeout=5)
        output = result.stdout.decode(errors='replace')
        cases[name] = (result.returncode == 0 and output.count('BOOTLOADER_REQUEST') == expected_requests
                       and output.count('INIT_STOPPED') == 1 and not result.stderr)
        (OUT / (name + '.stdout')).write_bytes(result.stdout)
        (OUT / (name + '.stderr')).write_bytes(result.stderr)
    uptime_state = OUT / 'fake-uptime-state'
    uptime_state.write_text('0\n')
    fake_busybox = OUT / 'fake-busybox'
    fake_busybox.write_text('''#!/bin/sh
[ "$1" = cut ] || exit 88
if [ "$(/bin/cat "$LYNX_TEST_UPTIME_STATE")" = 0 ]; then
    printf '1\\n' > "$LYNX_TEST_UPTIME_STATE"
    printf '10\\n'
else
    printf '190\\n'
fi
''')
    fake_busybox.chmod(0o700)
    harness = (f'''BB={fake_busybox}
cat() {{
    case "$1" in
        /etc/lynx/host-ip) printf '192.168.100.106\\n' ;;
        /etc/lynx/session-token) printf 'test-token\\n' ;;
        *) /bin/cat "$@" ;;
    esac
}}
log() {{ printf '%s\\n' "$*"; }}
. {ROOT / 'linux-port/openrc-handoff.sh'}
lynx_openrc_handoff
printf 'HANDOFF_RETURN=%s\\n' "$?"
''').encode()
    timeout_result = subprocess.run(['/bin/sh'], input=harness, capture_output=True,
                                    env=dict(os.environ, LYNX_TEST_UPTIME_STATE=str(uptime_state)), timeout=5)
    timeout_output = timeout_result.stdout.decode(errors='replace')
    cases['real-handoff-loop-expires-at-180-seconds'] = (
        timeout_result.returncode == 0 and
        'OPENRC_GATE_TIMEOUT; FASTBOOT_RETURN_REQUESTED' in timeout_output and
        'HANDOFF_RETURN=1' in timeout_output and uptime_state.read_text().strip() == '1')
    (OUT / 'real-handoff-timeout.stdout').write_bytes(timeout_result.stdout)
    (OUT / 'real-handoff-timeout.stderr').write_bytes(timeout_result.stderr)
    report = {'passed': all(cases.values()), 'checks': cases,
              'candidate_sha256': manifest['candidate_sha256'],
              'phone_contacted': False, 'flash_performed': False,
              'limits': 'Exact packed init tail with the sourced script and reboot executable replaced by test stubs; real gate timeout and MediaTek reset remain untested on handset.'}
    (OUT / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': report['passed'], 'result': str(OUT / 'result.json'),
                      'checks': cases}, indent=2))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
