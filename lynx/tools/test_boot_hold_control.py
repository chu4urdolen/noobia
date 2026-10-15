"""Run exact minimal-init guards/branches against saved fixtures; stub reboot."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT / 'linux-port'
original = PROJECT / 'init-boot-proof'
control = PROJECT / 'artifacts/busybox-minimal-hold-control/init-source'
fixtures = ROOT / 'tools/test-artifacts/boot-proof-guard-1791662566283189527'
output = ROOT / 'tools/test-artifacts' / ('boot-hold-control-' + str(time.time_ns()))
output.mkdir()
results = []
for name, source, fixture, expected_request in [('reference-bound', original, '0', True),
                                                 ('control-bound', control, '0', False),
                                                 ('reference-unbound', original, '1', False),
                                                 ('control-unbound', control, '1', False)]:
    text = source.read_text()
    body = text[text.index('wdt_ready=0'):]
    assert '/bin/boot-proof-reboot' not in body or source == original
    script = 'fixturebb() { "$@"; }; BB=fixturebb\nstop() { exit 0; }; log() { printf "%s\\n" "$*"; }\n'
    script += body.replace('/sys/', str(fixtures / fixture / 'sys') + '/').replace('/bin/boot-proof-reboot', "printf 'SIMULATED_NATIVE_REBOOT_REQUEST\\n'")
    path = output / (name + '.sh')
    path.write_text(script)
    process = subprocess.run(['sh', str(path)], capture_output=True, text=True, timeout=5)
    (output / (name + '.stdout')).write_text(process.stdout)
    (output / (name + '.stderr')).write_text(process.stderr)
    requested = 'SIMULATED_NATIVE_REBOOT_REQUEST' in process.stdout
    assert process.returncode == 0 and requested == expected_request
    if name == 'control-bound':
        assert 'HOLD_CONTROL_NO_REBOOT_REQUEST' in process.stdout
    results.append(dict(case=name, simulated_request=requested, passed=True))
report = dict(passed=True, cases=results, phone_contacted=False, reboot_executed=False,
              source_sha256={str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in [original, control]},
              limits='Exact guard/branch host fixtures with the reboot helper stubbed; no hardware causality established.')
(output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
print('Four control branch fixtures passed:', output / 'result.json')
