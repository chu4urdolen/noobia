"""Run the bounded V21 contact -> temperature -> battery -> OpenRC gate sequence.

Default mode is a local preflight. --listen contacts Lynx only after the
hash-pinned candidate is already booted and emitting its native beacon.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CANDIDATE = ROOT / 'linux-port/artifacts/openrc-gated-v21-fastboot-timeout'


def verified_candidate():
    result = json.loads((CANDIDATE / 'build-result.json').read_text())
    image = CANDIDATE / 'nord3-openrc-gated-candidate.img'
    digest = hashlib.sha256(image.read_bytes()).hexdigest()
    if result.get('state') != 'offline-openrc-gated-candidate-built' or digest != result.get('candidate_sha256'):
        raise ValueError('The local V20 candidate does not match its build receipt')
    if image.stat().st_mode & 0o777 != 0o600:
        raise ValueError('Candidate must remain private mode 0600')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--listen', action='store_true')
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--usb-unplugged-confirmed', action='store_true')
    args = parser.parse_args()
    candidate = verified_candidate()
    steps = ['pinned-contact', 'temperature-sensor-and-watch', 'battery-and-runtime-power', 'arm-openrc-gate']
    if args.self_test:
        assert candidate['candidate_sha256'] and steps[-1] == 'arm-openrc-gate'
        assert not args.listen
        print('Candidate hash, private mode, and staged order passed; no phone contacted.')
        return
    if not args.listen:
        print('Preflight passed. --listen starts the supervised multi-stage host workflow; Lynx must already be booted from this V21 image.')
        return
    if not args.usb_unplugged_confirmed:
        parser.error('The supervised handset sequence requires current confirmation that Lynx is physically unplugged from USB')

    os.umask(0o077)
    out = ROOT / 'logs' / ('openrc-handoff-sequence-' + str(time.time_ns()))
    out.mkdir(mode=0o700)
    report = {'state': 'starting', 'candidate_sha256': candidate['candidate_sha256'],
              'steps': steps, 'phone_contacted': False, 'flash_performed': False,
              'boot_or_partition_changed': False, 'started_ns': time.time_ns()}
    receipt = out / 'result.json'

    def save():
        tmp = receipt.with_suffix('.tmp')
        tmp.write_text(json.dumps(report, indent=2) + '\n')
        tmp.replace(receipt)

    def run(name, argv, timeout):
        report['state'] = name
        report['current_step_started_ns'] = time.time_ns()
        save()
        with (out / (name + '.stdout')).open('wb') as stdout, (out / (name + '.stderr')).open('wb') as stderr:
            proc = subprocess.run(argv, cwd=ROOT, stdout=stdout, stderr=stderr, timeout=timeout)
        report['current_step_exit_code'] = proc.returncode
        report['current_step_finished_ns'] = time.time_ns()
        save()
        if proc.returncode:
            raise ValueError(name + ' failed; raw output retained')
        return (out / (name + '.stdout')).read_text()

    def receipt_from(output, expression):
        match = re.search(expression, output)
        if not match:
            raise ValueError('Stage did not report its receipt path')
        path = Path(match.group(1)).resolve(strict=True)
        if not path.is_relative_to(ROOT / 'logs'):
            raise ValueError('Stage receipt escaped the Lynx logs directory')
        return path

    try:
        contact_output = run('pinned-contact', [sys.executable, str(ROOT / 'tools/lynx_wifi_v19_contact.py'), '--listen', '--seconds', '600'], 620)
        contact_dir = receipt_from(contact_output, r'Saved diagnostics: ([^\s]+)')
        contact = contact_dir / 'result.json'
        if json.loads(contact.read_text()).get('state') != 'native-ssh-available':
            raise ValueError('Pinned contact did not reach its completed state')
        report.update(phone_contacted=True, contact_receipt=str(contact))
        save()

        sensor_output = run('temperature-sensor-and-watch',
                            [sys.executable, str(ROOT / 'tools/lynx_sensor_trial.py'), '--listen', '--keep-running', '--usb-unplugged-confirmed', '--seconds', '300'], 330)
        sensor = receipt_from(sensor_output, r'SENSOR TRIAL FINISHED: ([^\s]+)')
        if json.loads(sensor.read_text()).get('state') != 'sensor-stage-returned':
            raise ValueError('Temperature sensor stage did not return cleanly')
        report['sensor_receipt'] = str(sensor)
        save()

        battery_output = run('battery-and-runtime-power',
                             [sys.executable, str(ROOT / 'tools/resume_battery_session.py'), '--start', '--usb-unplugged-confirmed', '--runtime-power'], 20)
        launch = json.loads(battery_output)
        worker_receipt = Path(launch['result']).resolve(strict=True)
        if not worker_receipt.is_relative_to(ROOT / 'logs'):
            raise ValueError('Battery resume receipt escaped the Lynx logs directory')
        deadline = time.monotonic() + 700
        while time.monotonic() < deadline:
            stage = json.loads(worker_receipt.read_text())
            if stage.get('state') in ('online', 'failed'):
                break
            time.sleep(1)
        else:
            raise ValueError('Battery/runtime-power workflow exceeded its bounded deadline')
        if stage.get('state') != 'online' or not stage.get('runtime_power_receipt'):
            raise ValueError('Battery/runtime-power stage did not reach its guarded online state')
        power = Path(stage['runtime_power_receipt']).resolve(strict=True)
        report.update(battery_resume_receipt=str(worker_receipt), runtime_power_receipt=str(power))
        save()

        run('arm-openrc-gate', [sys.executable, str(ROOT / 'tools/arm_openrc_handoff.py'),
                                '--session', str(contact), '--runtime-power', str(power), '--arm'], 45)
        report.update(state='openrc-handoff-gate-armed', finished_ns=time.time_ns())
    except Exception as error:
        report.update(state='failed-safe-or-incomplete', error=str(error), finished_ns=time.time_ns())
    save()
    print(json.dumps({'state': report['state'], 'result': str(receipt)}, indent=2))
    if report['state'] != 'openrc-handoff-gate-armed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
