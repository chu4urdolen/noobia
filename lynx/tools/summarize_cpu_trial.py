"""Verify saved CPU-trial evidence; emit a public result without raw logs."""
import argparse
import hashlib
import json
import re
from pathlib import Path

from lynx_wifi_v19_contact import proof_valid

ROOT = Path(__file__).resolve().parent.parent
BASELINE = '5ce2dbf8a7c132fa7e31f6be70aa76f83afe8c293e2cd5f02251a532486fd851'
PACK = '43ef800701f518317780b6c8afe1623740be0f22799822f0e912ff2286aba5de'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verify(receipt):
    folder = receipt.parent
    result = json.loads(receipt.read_text())
    ops = {op['name']: op for op in result['operations']}
    if not (result['native_identity_verified'] and result['stop_timer_armed']
            and result['cpu_frequency_modules_allowed']
            and result['trial_scope'] == ['soc-temperature', 'cpu-frequency']
            and not result['flash_performed'] and result['pack_sha256'] == PACK
            and result['sensor_stage_exit_code'] == 0
            and result['cpu_frequency_stage_exit_code'] == 0
            and result['second_sample_exit_code'] == 0):
        raise ValueError('Trial did not meet the expected success conditions')
    for op in result['operations']:
        data = (folder / (op['name'] + '.stdout')).read_bytes()
        if sha(data) != op['stdout_sha256'] or len(data) != op['stdout_bytes']:
            raise ValueError('Capture integrity failure: ' + op['name'])
    if not proof_valid((folder / 'identity.stdout').read_text(), ops['identity']['exit_code']):
        raise ValueError('Native identity proof failed')
    order = ['arm-stop-and-confirm', 'sensor-stage', 'cpu-frequency-stage',
             'kernel-and-sensors', 'cpu-and-battery-observation', 'request-poweroff']
    for first, second in zip(order, order[1:]):
        if ops[first]['finished_ns'] > ops[second]['started_ns']:
            raise ValueError('Unexpected operation order')
    inserted = []
    for name in ('sensor-stage', 'cpu-frequency-stage'):
        stage = (folder / (name + '.stdout')).read_text()
        starts = re.findall(r'(?m)^INSMOD_BEGIN (\S+)$', stage)
        returns = re.findall(r'(?m)^INSMOD_RETURN (\S+) status=(\d+)$', stage)
        if returns != [(module, '0') for module in starts]:
            raise ValueError('Module insertion did not return successfully')
        inserted.extend(starts)
    if inserted != ['nvmem_mtk_devinfo', 'soc_temp_lvts', 'oplus_omrg', 'mediatek_cpufreq_hw']:
        raise ValueError('Unexpected module insertions')
    cpu_stage = (folder / 'cpu-frequency-stage.stdout').read_text()
    if 'CPU_TEMPERATURE_GUARD_OK ' not in cpu_stage:
        raise ValueError('Temperature guard did not pass')
    sample = (folder / 'cpu-and-battery-observation.stdout').read_text()
    policies = {}
    for name, block in re.findall(r'CPU_POLICY (policy\d+)\n(.*?)(?=CPU_POLICY |COOLING |\Z)', sample, re.S):
        policies[name] = dict(re.findall(r'(?m)^(\w+)=(.*)$', block))
    expected = {'policy0': '0 1 2 3', 'policy4': '4 5 6', 'policy7': '7'}
    if set(policies) != set(expected):
        raise ValueError('Expected three CPU policies')
    for name, cpus in expected.items():
        p = policies[name]
        if (p['affected_cpus'] != cpus or p['scaling_driver'] != 'mtk-cpufreq-hw'
                or p['scaling_governor'] != 'schedutil'):
            raise ValueError('Unexpected CPU policy')
        for key in ('scaling_cur_freq', 'scaling_min_freq', 'scaling_max_freq'):
            p[key] = int(p[key])
        if not 0 < p['scaling_min_freq'] <= p['scaling_cur_freq'] <= p['scaling_max_freq']:
            raise ValueError('Frequency outside policy range')
    cooling = [{'name': name, 'type': kind, 'current_state': int(current), 'max_state': int(maximum)}
               for name, kind, current, maximum in re.findall(
                   r'(?m)^COOLING (cooling_device\d+)\n(thermal-cpufreq-\d+)\n(\d+)\n(\d+)$', sample)]
    if len(cooling) != 3 or any(c['max_state'] <= 0 for c in cooling):
        raise ValueError('Expected three CPU cooling interfaces')
    temps = {name: int(value) for name, value in re.findall(r'(?m)^thermal_zone\d+ (\S+)\n(-?\d+)$', sample)}
    gauge = '/sys/bus/i2c/devices/7-0055\nbq27541-battery\n' in sample
    kernel = (folder / 'kernel-and-sensors.stdout').read_text(errors='replace')
    if 'drivers/mtk-soc-temp-lvts' not in kernel or 'drivers/mediatek,devinfo' not in kernel:
        raise ValueError('Sensor/calibration bindings missing')
    boot = ROOT / 'linux-port/artifacts/busybox-wifi-ssh-twostage-v19/nord3-busybox-candidate.img'
    if sha(boot.read_bytes()) != BASELINE:
        raise ValueError('Baseline image changed')
    return {
        'milestone': 'Three stock CPU frequency policies and CPU cooling interfaces over native SSH',
        'native_identity_verified': True, 'modules_inserted': inserted,
        'cpu_policies': policies, 'frequency_units': 'kHz', 'cpu_cooling_interfaces': cooling,
        'temperatures_millidegrees_celsius': temps,
        'omrg_rule_disabled_observed': bool(re.search(r'(?m)^/sys/.*/ruler_enable\ndisabled$', sample)),
        'gauge_client_7_0055_observed': gauge,
        'battery_temperature_available': False, 'charging_settings_changed': False,
        'active_thermal_throttling_tested': False, 'power_reduction_measured': False,
        'flash_performed': False, 'baseline_image_sha256': BASELINE,
        'baseline_image_unchanged': True, 'pack_sha256': PACK,
        'independent_stop_timer_armed_before_module_load': True,
        'poweroff_requested': True,
        'physical_poweroff_confirmed': result.get('physical_poweroff_confirmed', False),
        'thermal_safety_fully_validated': False,
        'private_capture_sha256': {name: ops[name]['stdout_sha256'] for name in
                                  ('kernel-and-sensors', 'cpu-and-battery-observation')},
        'limits': 'One short supervised RAM-only trial. The largest core was at its policy maximum during the snapshot. Cooling registration does not prove throttling response, reduced heat, battery safety, suspend, or physical shutdown.'
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--receipt', type=Path, default=ROOT / 'logs/cpu-trial-1792101714003328176/result.json')
    args = parser.parse_args()
    result = verify(args.receipt.resolve())
    out = ROOT / 'linux-port/docs/CPU-HARDWARE-RESULT.json'
    out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'result': str(out), 'policies': len(result['cpu_policies']),
                      'cooling_interfaces': len(result['cpu_cooling_interfaces']),
                      'soc_celsius': result['temperatures_millidegrees_celsius']['soc_max'] / 1000}))


if __name__ == '__main__':
    main()
