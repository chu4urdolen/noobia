"""Semantic fixtures for healthy tracing and direct storage probe outcomes."""
import hashlib
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'linux-port/lynx-classify-driver-trace-v3.awk'


def main():
    out = ROOT / 'tools/test-artifacts' / ('driver-trace-v3-classifier-' + str(time.time_ns()))
    out.mkdir()
    health = 'shell-123 [000] 1.0: health_pid: (syscall) ret=123\n'
    probe = lambda value: 'worker-234 [001] 2.0: mtk_probe_return: (probe) ret=' + str(value) + '\n'
    specifications = [
        ('empty', '', 4), ('wrong-pid', health.replace('ret=123', 'ret=999') + probe(0), 4),
        ('no-probe', health, 5), ('entry-only', health + 'worker: mtk_probe_enter: (probe)\n', 5),
        ('malformed-return', health + 'worker: mtk_probe_return: no retval\n', 5),
        ('deferred', health + probe(-517), 6), ('error', health + probe(-22), 7),
        ('success', health + probe(0), 2), ('last-success', health + probe(-517) + probe(0), 2),
        ('last-defer', health + probe(0) + probe(-517), 6),
        ('generic-success-insufficient', health + 'worker: init_return: (generic) ret=0\n', 5),
        ('malformed-after-success', health + probe(0) + 'worker: mtk_probe_return: no retval\n', 5),
    ]
    cases = []
    for name, raw, expected in specifications:
        (out / (name + '.trace')).write_text(raw)
        result = subprocess.run(['awk', '-v', 'expected_pid=123', '-f', str(SOURCE)], input=raw, text=True, capture_output=True, check=True)
        (out / (name + '.output')).write_text(result.stdout)
        assert int(result.stdout.split()[0]) == expected, (name, result.stdout)
        cases.append({'case': name, 'expected_code': expected})
    report = {'passed': True, 'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
              'cases': cases, 'phone_contacted': False, 'limits': 'Host parser semantics; physical probe and trace delivery unverified.'}
    path = out / 'result.json'
    path.write_text(json.dumps(report, indent=2) + '\n')
    print(path)


if __name__ == '__main__':
    main()
