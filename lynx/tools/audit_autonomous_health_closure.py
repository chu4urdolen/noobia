"""Audit the inert health pack against the exact successful Lynx module trial.

No phone connection or boot image modification. Missing stock-preloaded modules
are a hard failure: a future boot script must check them before any insertion.
"""
import hashlib
import io
import json
import os
import re
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / 'linux-port'
PACK = PORT / 'artifacts/autonomous-health-inputs'
TRIAL = ROOT / 'logs/gauge-identity-trial-1792263255844252719'
OUT = PORT / 'artifacts/autonomous-health-closure'
STAGES = (
    ('soc-temperature', 'sensor-stage.stdout'),
    ('cpu-frequency', 'cpu-frequency-stage.stdout'),
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def parse_plan(raw):
    rows = []
    for line in raw.decode().splitlines():
        fields = line.split()
        if len(fields) != 2 or not re.fullmatch(r'[a-zA-Z0-9_]+', fields[0]) or not re.fullmatch(r'[a-zA-Z0-9_.-]+\.ko', fields[1]):
            raise ValueError('Malformed reviewed module plan')
        rows.append(tuple(fields))
    if not rows or len(rows) != len(set(name for name, _ in rows)):
        raise ValueError('Empty or duplicate reviewed module plan')
    return rows


def audit_stage(stage, trial_name, files):
    rows = parse_plan(files['review/plans/' + stage + '.list'])
    log = (TRIAL / trial_name).read_text()
    if 'STAGE_INSERTIONS_RETURNED ' + stage not in log:
        raise ValueError('Live stage did not complete: ' + stage)
    inserted = []
    preloaded = []
    for name, filename in rows:
        packed = 'modules/' + filename
        if packed in files:
            if (f'INSMOD_BEGIN {name}' not in log or
                    f'INSMOD_RETURN {name} status=0' not in log):
                raise ValueError('Packed module lacks successful live insertion: ' + name)
            inserted.append({'name': name, 'file': packed, 'sha256': sha(files[packed])})
        else:
            if f'ALREADY_LOADED {name}' not in log:
                raise ValueError('Omitted plan module lacks live preloaded proof: ' + name)
            preloaded.append(name)
    actual = re.findall(r'^(?:INSMOD_BEGIN|ALREADY_LOADED) ([a-zA-Z0-9_]+)$', log, re.M)
    if actual != [name for name, _ in rows]:
        raise ValueError('Live plan order differs: ' + stage)
    return {'stage': stage, 'inserted': inserted, 'must_be_preloaded_at_boot': preloaded,
            'trial_log': str((TRIAL / trial_name).relative_to(ROOT)),
            'trial_log_sha256': sha(log.encode())}


def main():
    os.umask(0o077)
    report = json.loads((PACK / 'result.json').read_text())
    archive = (PACK / 'inputs.tar.gz').read_bytes()
    if not report.get('roundtrip_verified') or sha(archive) != report.get('archive_sha256'):
        raise ValueError('Inert input archive or manifest differs')
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as tar:
        files = {member.name: tar.extractfile(member).read() for member in tar
                 if member.isfile()}
    for name, info in report['files'].items():
        if sha(files[name]) != info['sha256'] or len(files[name]) != info['bytes']:
            raise ValueError('Packed file differs: ' + name)
    stages = [audit_stage(stage, log, files) for stage, log in STAGES]
    packed_names = {entry['file'] for stage in stages for entry in stage['inserted']}
    if packed_names != {name for name in files if name.startswith('modules/') and name not in
                        ('modules/lynx-gauge-sample.ko', 'modules/lynx-battery-monitor.ko')}:
        raise ValueError('Extra or missing stock driver in inert pack')
    for filename in ('modules/lynx-gauge-sample.ko', 'modules/lynx-battery-monitor.ko'):
        if filename not in files:
            raise ValueError('Missing gauge module: ' + filename)
    result = {
        'state': 'autonomous-health-module-closure-audited',
        'created_ns': time.time_ns(), 'phone_contacted': False,
        'flash_performed': False, 'archive_sha256': sha(archive),
        'stages': stages,
        'identity_query_requires_same_boot_device_type': 42495,
        'boot_requirement': 'Check every must_be_preloaded_at_boot module in /sys/module before insertion; run DT/calibration and live temperature guards; re-query gauge identity on every boot.',
        'limits': 'Saved successful live insertion order is evidence, not proof that unattended cold-boot insertion is safe. No autonomous boot script is activated.'
    }
    OUT.mkdir(mode=0o700, exist_ok=True)
    path = OUT / 'result.json'
    path.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'state': result['state'], 'result': str(path),
                      'preloaded': [s['must_be_preloaded_at_boot'] for s in stages]}))


if __name__ == '__main__':
    main()
