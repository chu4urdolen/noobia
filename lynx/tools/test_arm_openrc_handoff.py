"""Receipt-only tests for the opt-in OpenRC handoff armer; never contacts Lynx."""
import importlib.util
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / 'tools/arm_openrc_handoff.py'
OUT = ROOT / 'linux-port/artifacts' / f'openrc-handoff-armer-check-{time.time_ns()}'
spec = importlib.util.spec_from_file_location('arm_openrc_handoff', TOOL)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def main():
    OUT.mkdir(mode=0o700)
    build = json.loads((module.BASE / 'build-validation.json').read_text())
    session = {'state': 'native-ssh-available', 'native_ssh_verified': True,
               'session_token': build['session_token'], 'phone_ip': '192.168.100.5'}
    power = {'state': 'ready', 'mode': 'apply', 'native_identity_verified': True,
             'boot_id': 'cf5e2ccf-5c49-485e-9403-b12e3d6bb574'}
    session_path, power_path = OUT / 'session.json', OUT / 'runtime-power.json'
    session_path.write_text(json.dumps(session))
    power_path.write_text(json.dumps(power))
    module.audit(session_path, power_path)
    cases = {'valid_receipts_accepted': True}
    bad_session = dict(session, session_token='wrong-token')
    session_path.write_text(json.dumps(bad_session))
    try:
        module.audit(session_path, power_path)
        cases['wrong_token_rejected'] = False
    except ValueError:
        cases['wrong_token_rejected'] = True
    session_path.write_text(json.dumps(session))
    bad_power = dict(power, mode='check')
    power_path.write_text(json.dumps(bad_power))
    try:
        module.audit(session_path, power_path)
        cases['verify_only_receipt_rejected'] = False
    except ValueError:
        cases['verify_only_receipt_rejected'] = True
    power_path.write_text(json.dumps(power))
    bad_session = dict(session, phone_ip='192.168.8.5')
    session_path.write_text(json.dumps(bad_session))
    try:
        module.audit(session_path, power_path)
        cases['off_network_ip_rejected'] = False
    except ValueError:
        cases['off_network_ip_rejected'] = True
    report = {'state': 'openrc-handoff-armer-tests-passed' if all(cases.values()) else 'failed',
              'created_ns': time.time_ns(), 'checks': cases, 'phone_contacted': False,
              'marker_written': False, 'flash_performed': False}
    (OUT / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    if not all(cases.values()):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
