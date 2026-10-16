"""Summarize hash-verified, paired CPU idle captures without phone contact."""
import argparse
import hashlib
import json
import re
from pathlib import Path


def summarize(receipt):
    report = json.loads(receipt.read_text())
    if not report.get('native_identity_verified'):
        raise ValueError('Native SSH identity was not verified')
    operation = next(op for op in report['operations'] if op['name'] == 'command')
    raw = receipt.with_name('command.stdout').read_bytes()
    if operation['exit_code'] != 0 or hashlib.sha256(raw).hexdigest() != operation['stdout_sha256']:
        raise ValueError('Failed command or capture hash mismatch')
    snapshots = []
    pattern = re.compile(r'^/sys/devices/system/cpu/(cpu\d+)/cpuidle/(state\d+) (.+)$')
    for block in raw.decode().split('SNAPSHOT ')[1:]:
        lines = block.splitlines()
        snapshot = {'label': lines[0], 'uptime_seconds': float(lines[1].split()[0]), 'states': {}}
        for line in lines[2:]:
            match = pattern.fullmatch(line)
            if match:
                fields = dict(field.split('=', 1) for field in match[3].split())
                snapshot['states'][match[1] + '/' + match[2]] = {
                    key: fields[key] if key == 'name' else int(fields[key])
                    for key in ('name', 'disable', 'usage', 'time', 'rejected')}
            elif re.fullmatch(r'(temperature_millidegrees_celsius|gauge_current_ma_signed|capacity_percent)=-?\d+', line):
                key, value = line.split('=')
                snapshot[key] = int(value)
        if not snapshot['states']:
            raise ValueError('Snapshot has no CPU idle states')
        snapshots.append(snapshot)
    if len(snapshots) < 2:
        raise ValueError('Need at least two snapshots')
    intervals = []
    for before, after in zip(snapshots, snapshots[1:]):
        elapsed = after['uptime_seconds'] - before['uptime_seconds']
        if elapsed <= 0 or before['states'].keys() != after['states'].keys():
            raise ValueError('Nonpositive interval or changed idle state inventory')
        deltas = {}
        for key, state in before['states'].items():
            new = after['states'][key]
            if state['name'] != new['name']:
                raise ValueError('Idle state name changed')
            delta = {field: new[field] - state[field] for field in ('usage', 'time', 'rejected')}
            if any(value < 0 for value in delta.values()):
                raise ValueError('Idle counters decreased')
            deltas[key] = {'name': state['name'], **delta}
        cpus = {key.split('/')[0] for key in deltas}
        rejected = sum(state['rejected'] for state in deltas.values())
        wfi_time = sum(state['time'] for state in deltas.values() if state['name'] == 'WFI')
        intervals.append({'from': before['label'], 'to': after['label'], 'elapsed_seconds': elapsed,
                          'rejected_entries': rejected, 'rejected_entries_per_second': rejected / elapsed,
                          'accounted_wfi_time_per_cpu_wall_time': wfi_time / (elapsed * 1e6 * len(cpus)),
                          'short_transition_interval': elapsed < 5,
                          'state_deltas': deltas})
    return {'capture_sha256': hashlib.sha256(raw).hexdigest(), 'snapshots': snapshots, 'intervals': intervals,
            'notes': ['WFI time is microseconds; the ratio uses all observed CPUs.',
                      'Counters update on idle exit: sleep spanning a snapshot boundary can make the ratio exceed one.',
                      'Short transition intervals are not steady-state measurements.',
                      'Gauge current snapshots do not establish average power or battery life.',
                      'Snapshot collection is sequential, so interval boundaries are approximate.']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    result = summarize(args.receipt)
    output = args.receipt.with_name('idle-analysis.json')
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'analysis': str(output), 'intervals': [
        {key: value for key, value in interval.items() if key != 'state_deltas'} for interval in result['intervals']]}))


if __name__ == '__main__':
    main()
