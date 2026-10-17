"""Bundle only reviewed Lynx health inputs for a future guarded boot stage.

The archive is inert: it contains no boot hook and is never sent to the phone.
"""
import gzip
import hashlib
import io
import json
import os
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / 'linux-port'
THERMAL = PORT / 'artifacts/thermal-ssh-pack-1792101216718173026/thermal-ssh-pack.tar.gz'
GAUGE = PORT / 'artifacts/gauge-module-basis-1792105646594458259'
MONITOR = PORT / 'artifacts/gauge-module-basis-1792107325426159905'
OUT = PORT / 'artifacts/autonomous-health-inputs'
THERMAL_SHA = '43ef800701f518317780b6c8afe1623740be0f22799822f0e912ff2286aba5de'
NAMES = ('nvmem_mtk_devinfo', 'soc_temp_lvts', 'oplus_omrg', 'mediatek_cpufreq_hw')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    os.umask(0o077)
    if OUT.exists():
        raise ValueError('Refuse to replace an autonomous health input pack')
    raw = THERMAL.read_bytes()
    if sha(raw) != THERMAL_SHA:
        raise ValueError('Reviewed thermal/CPU pack differs')
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
        members = archive.getmembers()
        if any(not member.isfile() or member.name.startswith('/') or '..' in Path(member.name).parts
               for member in members):
            raise ValueError('Unsafe thermal pack entry')
        thermal = {member.name: archive.extractfile(member).read() for member in members}
    source_manifest = json.loads(thermal['manifest.json'])
    if not (source_manifest.get('live_trial_eligible') and
            source_manifest.get('trial_scope') == ['soc-temperature', 'cpu-frequency']):
        raise ValueError('Thermal/CPU pack lacks the reviewed scope')
    for line in thermal['SHA256SUMS'].decode().splitlines():
        digest, name = line.split('  ', 1)
        if sha(thermal[name]) != digest:
            raise ValueError('Thermal pack internal hash differs: ' + name)

    selected = {}
    module_provenance = {}
    for name in NAMES:
        info = source_manifest['modules'][name]
        path = 'modules/' + info['file']
        data = thermal[path]
        if sha(data) != info['sha256'] or len(data) != info['bytes']:
            raise ValueError('Stock module differs: ' + name)
        selected[path] = data
        module_provenance[name] = {'file': path, 'sha256': sha(data), 'bytes': len(data)}
    for name in ('DT-SHA256SUMS', 'DT-ABSENT', 'DEVINFO-MIN-BYTES',
                 'cpu-temperature-guard.sh', 'plans/soc-temperature.list',
                 'plans/cpu-frequency.list'):
        selected['review/' + name] = thermal[name]

    for label, basis, source in (
        ('gauge-identity', GAUGE, PORT / 'lynx-gauge-identity.c'),
        ('battery-monitor', MONITOR, PORT / 'lynx-battery-monitor.c'),
    ):
        build = json.loads((basis / 'build-result.json').read_text())
        module = basis / 'module' / ('lynx-gauge-sample.ko' if label == 'gauge-identity' else 'lynx-battery-monitor.ko')
        data = module.read_bytes()
        if not (build.get('passed') and build.get('lto_and_cfi_enabled') and
                sha(data) == build.get('module_sha256') and
                sha(source.read_bytes()) == build.get('source_sha256')):
            raise ValueError('Reviewed gauge module/source differs: ' + label)
        selected['modules/' + module.name] = data
        module_provenance[label] = {'file': 'modules/' + module.name,
                                    'sha256': sha(data), 'bytes': len(data),
                                    'source_sha256': build['source_sha256']}
    for name in ('thermal-watch.sh', 'battery-watch.sh', 'thermal-cooling-watch.sh',
                 'lynx-health-supervisor.sh', 'wfi-fallback.sh'):
        selected['scripts/' + name] = (PORT / name).read_bytes()

    manifest = {
        'state': 'reviewed-inert-health-inputs', 'created_ns': time.time_ns(),
        'phone_contacted': False, 'flash_performed': False,
        'thermal_cpu_source_sha256': THERMAL_SHA,
        'kernel_release': source_manifest['kernel_release'],
        'modules': module_provenance,
        'files': {name: {'bytes': len(data), 'sha256': sha(data)}
                  for name, data in sorted(selected.items())},
        'auto_boot_hook_present': False,
        'limits': 'Inputs only. Automatic module insertion, gauge identification, startup timing and failure recovery require a separately reviewed boot stage and phone trial.'
    }
    selected['manifest.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode='wb', filename='', mtime=0) as zipped:
        with tarfile.open(fileobj=zipped, mode='w', format=tarfile.USTAR_FORMAT) as archive:
            for name, data in sorted(selected.items()):
                info = tarfile.TarInfo(name)
                info.size = len(data)
                info.mode = 0o600
                info.mtime = 0
                archive.addfile(info, io.BytesIO(data))
    packed = buffer.getvalue()
    with tarfile.open(fileobj=io.BytesIO(packed), mode='r:gz') as archive:
        roundtrip = {member.name: archive.extractfile(member).read() for member in archive}
    if roundtrip != selected:
        raise ValueError('Autonomous health input archive round trip differs')
    OUT.mkdir(mode=0o700)
    target = OUT / 'inputs.tar.gz'
    target.write_bytes(packed)
    target.chmod(0o600)
    manifest.update(archive_sha256=sha(packed), archive_bytes=len(packed),
                    roundtrip_verified=True)
    (OUT / 'result.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'state': manifest['state'], 'archive_sha256': manifest['archive_sha256'],
                      'archive_bytes': len(packed), 'result': str(OUT / 'result.json')}))


if __name__ == '__main__':
    main()
