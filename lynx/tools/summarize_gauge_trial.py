"""Verify completed gauge-trial streams and preserve a conservative analysis."""
import argparse
import hashlib
import json
import re
from pathlib import Path

import lynx_gauge_trial as gauge
from lynx_wifi_v19_contact import proof_valid


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--identity-query', action='store_true')
    args = parser.parse_args()
    if args.identity_query:
        import lynx_gauge_identity_trial
    receipt = args.receipt.resolve()
    trial = json.loads(receipt.read_text())
    if 'finished_ns' not in trial:
        raise ValueError('Trial still running: do not summarize incomplete capture')
    folder = receipt.parent
    operations = {op['name']: op for op in trial['operations']}
    for op in trial['operations']:
        data = (folder / (op['name'] + '.stdout')).read_bytes()
        if len(data) != op['stdout_bytes'] or sha(data) != op['stdout_sha256']:
            raise ValueError('Capture integrity failure: ' + op['name'])
    identity = (folder / 'identity.stdout').read_text() if 'identity' in operations else ''
    verified = ('identity' in operations and proof_valid(identity, operations['identity'].get('exit_code')))
    command = (folder / 'gauge-sample.stdout').read_text(errors='replace') if 'gauge-sample' in operations else ''
    marker = 'GAUGE_DEVICE_TYPE_REPLY=1' if args.identity_query else 'GAUGE_RAW_MODEL_UNVERIFIED=1'
    raw = re.search(r'(?m)^' + marker + r'\n(\d+)\nGAUGE_UNLOADED=0$', command)
    word = int(raw.group(1)) if raw else None
    kernel = (folder / 'kernel-and-sensors.stdout').read_text(errors='replace') if 'kernel-and-sensors' in operations else ''
    kernel_pattern = r'LYNX_GAUGE_DEVICE_TYPE word=(\d+) query=0x0001' if args.identity_query else r'LYNX_GAUGE_RAW register=0x06 word=(\d+) model_unverified=1'
    kernel_words = [int(n) for n in re.findall(kernel_pattern, kernel)]
    timer_before_probe = ('arm-stop-and-confirm' in operations and 'gauge-sample' in operations
                          and operations['arm-stop-and-confirm']['finished_ns'] < operations['gauge-sample']['started_ns'])
    protective_monitor = trial.get('stop_timer_armed') or (trial.get('keep_running_requested') and trial.get('thermal_watch_armed'))
    successful = (verified and not trial['flash_performed'] and protective_monitor
                  and timer_before_probe and trial.get('sensor_stage_exit_code') == 0
                  and trial.get('cpu_frequency_stage_exit_code') == 0
                  and operations.get('gauge-sample', {}).get('exit_code') == 0
                  and word is not None and 0 <= word <= 65535
                  and word in kernel_words and 'GAUGE_INSMOD_RETURN=0' in command
                  and trial['extra_diagnostic_preflight']['module_sha256'] == gauge.MODULE_SHA)
    result = {'capture_integrity_verified': True, 'native_identity_verified': verified,
              'one_shot_raw_read_verified': bool(successful), 'raw_register_word': word,
              'kernel_raw_words': kernel_words, 'gauge_model_verified': False,
              'battery_temperature_validated': False, 'thermal_safety_validated': False,
              'ram_module_unloaded_marker': 'GAUGE_UNLOADED=0' in command,
              'protective_monitor_before_probe': bool(protective_monitor and timer_before_probe),
              'timed_shutdown_armed': trial.get('stop_timer_armed',False),
              'temperature_watch_armed': trial.get('thermal_watch_armed',False),
              'flash_performed': trial['flash_performed'],
              'poweroff_requested': 'request-poweroff' in operations,
              'physical_poweroff_confirmed': trial.get('physical_poweroff_confirmed', False),
              'limits': 'The raw gauge word is not independently identified/calibrated battery temperature. No physical power-off inference is made from SSH loss.',
              'operation_exit_codes': {name: op.get('exit_code') for name, op in operations.items()}}
    if args.identity_query:
        families = {0xffa5: 'BQ28Z610 stock-driver family', 0xa5ff: 'ZY0603',
                    0x0541: 'BQ27541', 0x0421: 'BQ27411', 0x0602: 'ZY0602'}
        result.update(identity_query_verified=bool(successful), raw_device_type_hex=f'0x{word:04x}' if word is not None else None,
                      stock_driver_family=families.get(word) if successful else None,
                      family_response_recognized=bool(successful and word in families))
    (folder / 'analysis.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'analysis': str(folder / 'analysis.json'), **result}, indent=2))


if __name__ == '__main__':
    main()
