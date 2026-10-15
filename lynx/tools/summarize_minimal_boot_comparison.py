"""Collate the fixed timed A/B receipts offline; keep inference conditional."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT / 'linux-port'


def read(path):
    return json.loads(path.read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def reset_evidence(path):
    text = path.read_text()
    mode = re.search(r'NONRST_REG2:\s*(0x[0-9a-fA-F]+)', text)
    status = re.search(r'RAM_CONSOLE wdt status\s*(0x[0-9a-fA-F]+)', text)
    stage = re.search(r'\[RGU\] rst from:\s*([^\r\n]+)', text)
    require(mode is not None and status is not None and stage is not None, 'Reset evidence missing')
    return dict(nonrst_reg2=int(mode.group(1), 16), watchdog_status=int(status.group(1), 16), raw_reset_stage=stage.group(1).strip(), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def main():
    positive_path = ROOT / 'logs/boot-a-timed-minimal-reboot-trial-1791668852862284083.json'
    control_path = ROOT / 'logs/boot-a-timed-minimal-hold-trial-1791668942994926109.json'
    positive, control = read(positive_path), read(control_path)
    arms = []
    for name, trial, path in [('reboot', positive, positive_path), ('hold', control, control_path)]:
        require(trial['comparison_arm'] == name, 'Trial arm mismatch')
        require(len(trial['operations']) == 2 and all(item['exit_code'] == 0 for item in trial['operations']), 'Trial commands incomplete')
        require(trial['operations'][0]['command'][3:5] == ['flash', 'boot_a'], 'Unexpected flash target')
        require(trial['operations'][1]['command'][3:] == ['reboot'], 'Unexpected reboot type')
        observer = read(Path(trial['usb_observer_receipt']))
        require(observer['observation_complete'] and observer['error'] is None, 'Observation incomplete or failed')
        require(observer['phone_commands_sent'] is False, 'Collector must be passive')
        reboot_ns = trial['operations'][1]['started_ns']
        events = [dict(event, seconds_after_reboot=(event['wall_time_ns'] - reboot_ns) / 1e9) for event in observer['events']]
        arms.append(dict(arm=name, trial_receipt=str(path), observer_receipt=trial['usb_observer_receipt'], image_sha256=trial['images'][0]['sha256'], fastboot_return_observed=observer['fastboot_return_observed'], observed_seconds_after_reboot=observer['elapsed_seconds'] - (reboot_ns - observer['started_ns']) / 1e9, events=events))
    validation = read(PROJECT / 'docs/boot-hold-control-validation.json')
    before = reset_evidence(ROOT / 'logs/pllk-1791668845978416528.clean.txt')
    after = reset_evidence(ROOT / 'logs/pllk-1791668922230977251.clean.txt')
    signature_reproduced = before['nonrst_reg2'] & 15 == 0 and after['nonrst_reg2'] & 15 == 3 and after['watchdog_status'] == 2
    report = dict(arms=arms, only_changed_archive_entry=validation['only_changed_archive_entry'],
                  software_return_signature_reproduced=signature_reproduced,
                  reset_evidence_before=before, reset_evidence_after=after,
                  before_positive_reset_log='logs/pllk-1791668845978416528.json',
                  after_positive_reset_log='logs/pllk-1791668922230977251.json',
                  positive_stock_undo='logs/boot-a-timed-minimal-reboot-trial-1791668928584614474.json',
                  positive_user_button_confirmation='pending; do not infer an answer',
                  control_user_button_confirmation='not yet recorded',
                  direct_native_console_marker_observed=False,
                  conclusive_native_pid1_proof=False,
                  last_persistent_boot_a='minimal hold control; stock undo pending physical Fastboot return',
                  conclusion='If buttons/cable were untouched, a reboot-arm return and no matching control return support native init causality; proprietary image-dependent bootloader behavior and absence of direct native output remain limitations.',
                  limitations=['USB transition timing resolution approximately 0.25 seconds.', 'No-return control cannot itself prove that native PID1 reached its hold.', 'Original successful trial and this repeat are indirect evidence; retain raw reset-stage label lk.'])
    for arm in arms:
        arm['trial_receipt_sha256'] = hashlib.sha256(Path(arm['trial_receipt']).read_bytes()).hexdigest()
        arm['observer_receipt_sha256'] = hashlib.sha256(Path(arm['observer_receipt']).read_bytes()).hexdigest()
    output = PROJECT / 'docs/timed-minimal-boot-comparison.json'
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(output)


if __name__ == '__main__':
    main()
