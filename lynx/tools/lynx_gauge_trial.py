"""Reviewed one-shot raw gauge read after the proven sensor/CPU RAM stages.

No image/partition changes or charging/calibration commands. Start listening
before the human powers Lynx on with USB unplugged. Raw model unverified.
"""
import hashlib
import json
import subprocess
from pathlib import Path

import lynx_cpu_trial  # Select the frozen, hardware-proven sensor/CPU pack.
from lynx_cpu_trial import trial

ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / 'linux-port'
BASIS = PORT / 'artifacts/gauge-module-basis-1792104554981554338'
MODULE = BASIS / 'module/lynx-gauge-sample.ko'
SOURCE = PORT / 'lynx-gauge-sample.c'
MODULE_SHA = '9b40f97120dc87329ef42aa74742dca51ddb56f40e78dcfa6df7b7c37662e374'
SOURCE_SHA = 'c646f5c5897d3dcced770ec3c3c981ce2a59bff61ab7d1b913acf1ba54ed37c4'
VM = PORT / 'artifacts/emulated-gauge-sample-1792104678354338978/result.json'
LOGIC = PORT / 'artifacts/gauge-reader-logic-1792103944676969260/result.json'
COMMAND_TEST = PORT / 'artifacts/gauge-command-check-1792104959339213259/result.json'

COMMAND = r'''set -e
BB=/bin/busybox
P=/sys/bus/i2c/devices/7-0055
[ "$($BB cat "$P/name")" = bq27541-battery ]
[ ! -e "$P/driver" ] && [ ! -L "$P/driver" ]
[ -e "$P/of_node/qcom,batt_bq28z610" ]
[ ! -e /sys/module/lynx_gauge_sample ]
[ ! -e /run/lynx/gauge-sample.started ]
kill -0 "$($BB cat /run/lynx/thermal-stop.pid)"
echo 'MODULE_SHA  /run/lynx/gauge-sample.ko' | $BB sha256sum -c -
. /run/lynx/thermal-cpu-trial/cpu-temperature-guard.sh
lynx_cpu_temperature_guard
echo started > /run/lynx/gauge-sample.started
echo GAUGE_INSMOD_BEGIN
$BB insmod /run/lynx/gauge-sample.ko allow_raw_read=1
echo GAUGE_INSMOD_RETURN=0
echo GAUGE_RAW_MODEL_UNVERIFIED=1
$BB cat "$P/raw_temperature_word"
$BB rmmod lynx_gauge_sample
echo GAUGE_UNLOADED=0
'''.replace('MODULE_SHA', MODULE_SHA)


def validate_extra(require_command_test=True):
    data = MODULE.read_bytes()
    build = json.loads((BASIS / 'build-result.json').read_text())
    vm, logic = json.loads(VM.read_text()), json.loads(LOGIC.read_text())
    if hashlib.sha256(data).hexdigest() != MODULE_SHA:
        raise ValueError('Gauge module differs from reviewed/VM-tested binary')
    if not build['passed'] or build['module_sha256'] != MODULE_SHA or not build['lto_and_cfi_enabled']:
        raise ValueError('Stock ABI/CFI build checks missing')
    if not vm['passed'] or vm['module_sha256'] != MODULE_SHA or vm['phone_contacted']:
        raise ValueError('Exact module stock-kernel VM test missing')
    if (not logic['passed'] or logic['source_sha256'] != SOURCE_SHA
            or hashlib.sha256(SOURCE.read_bytes()).hexdigest() != SOURCE_SHA
            or build['source_sha256'] != SOURCE_SHA):
        raise ValueError('Source/logic/build identity differs')
    check = subprocess.run(['sh', '-n'], input=COMMAND.encode(), capture_output=True)
    if check.returncode:
        raise ValueError('Remote command syntax failed')
    if require_command_test:
        if '/thermal-watch.pid' in COMMAND:
            candidates=[json.loads(f.read_text()) for f in (PORT/'artifacts').glob('gauge-command-check-*/result.json')]
            matching=[r for r in candidates if r.get('passed') and r.get('command_sha256')==hashlib.sha256(COMMAND.encode()).hexdigest() and r.get('module_sha256')==MODULE_SHA]
            if not matching:raise ValueError('Continuous command needs matching fixture test')
            tested=matching[-1]
        else:tested = json.loads(COMMAND_TEST.read_text())
        if not tested['passed'] or tested['command_sha256'] != hashlib.sha256(COMMAND.encode()).hexdigest() or tested['module_sha256'] != MODULE_SHA:
            raise ValueError('Remote command has no matching successful fixture test')
    return data


def sample(run, ip):
    data = validate_extra()
    _, rc = run(ip, 'upload-gauge-module',
                'test ! -e /run/lynx/gauge-sample.ko && cat > /run/lynx/gauge-sample.ko', stdin=data)
    if rc != 0:
        return {'exit_code': rc, 'state': 'upload-failed', 'model_verified': False}
    _, rc = run(ip, 'gauge-sample', COMMAND, timeout=10)
    return {'exit_code': rc, 'state': 'command-returned' if rc == 0 else 'failed-or-hung',
            'model_verified': False, 'module_sha256': MODULE_SHA}


if __name__ == '__main__':
    validate_extra()
    trial.TRIAL_PREFIX = 'gauge-trial-'
    trial.POST_CPU_HOOK = sample
    trial.EXTRA_DIAGNOSTIC = {'kind': 'one-shot raw register word, model unverified',
                              'module_sha256': MODULE_SHA, 'source_sha256': SOURCE_SHA,
                              'stock_kernel_vm_passed': True, 'physical_probe_previously_tested': False}
    trial.main()
