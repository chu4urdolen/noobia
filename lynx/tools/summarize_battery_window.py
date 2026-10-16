"""Offline summary of hash-verified host battery samples in a time window."""
import argparse
import hashlib
import json
import statistics
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--since-ns', type=int, required=True)
    parser.add_argument('--until-ns', type=int)
    parser.add_argument('--label', required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    samples, failures, duplicates = [], [], 0
    seen = set()
    for line in (args.log / 'samples.jsonl').read_text().splitlines():
        entry = json.loads(line)
        if entry['started_ns'] < args.since_ns or (args.until_ns and entry['finished_ns'] > args.until_ns):
            continue
        raw = (args.log / (entry['name'] + '.stdout')).read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry['stdout_sha256']:
            raise ValueError('Capture hash mismatch: ' + entry['name'])
        values = dict(line.split('=', 1) for line in raw.decode().splitlines() if '=' in line and ' ' not in line)
        if entry['exit_code'] != 0 or any(values.get(key) != '0' for key in
                                       ('temperature_error', 'voltage_error', 'current_error', 'capacity_error')):
            failures.append(entry['name'])
            continue
        stamp = values['sample_uptime_seconds']
        if stamp in seen:
            duplicates += 1
            continue
        seen.add(stamp)
        samples.append({'sample_uptime_seconds': float(stamp),
                        **{key: int(values[key]) for key in ('gauge_current_ma_signed',
                           'temperature_millidegrees_celsius', 'capacity_percent', 'pack_voltage_mv')}})
    if not samples:
        raise ValueError('No valid distinct samples in window')
    result = {'label': args.label, 'samples': len(samples), 'failed_samples': failures,
              'duplicate_cached_samples': duplicates, 'since_ns': args.since_ns, 'until_ns': args.until_ns,
              'sample_span_seconds': samples[-1]['sample_uptime_seconds'] - samples[0]['sample_uptime_seconds'],
              'fields': {}, 'notes': ['Discrete cached gauge samples under SSH polling, not measured idle power.',
                                    'Mean is unweighted; do not infer battery life or causal savings from this alone.']}
    for key in samples[0]:
        if key == 'sample_uptime_seconds':
            continue
        values = [sample[key] for sample in samples]
        result['fields'][key] = {'minimum': min(values), 'maximum': max(values),
                                 'mean': statistics.mean(values), 'median': statistics.median(values)}
    rendered = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.write_text(rendered)
    print(rendered, end='')


if __name__ == '__main__':
    main()
