"""Passively save live Lynx health startup logs over pinned SSH."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
COMMAND = ('while [ ! -e /run/lynx/health-bootstrap-child.log ]; do '
           '/bin/busybox sleep 1; done; '
           'printf "LYNX_HEALTH_STREAM_START\\n"; '
           '/bin/busybox tail -n 0 -f '
           '/run/lynx/health-bootstrap-child.log /run/lynx/boot.log')


def save(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2) + '\n')
    temp.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--observer-receipt', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--seconds', type=int, default=600)
    args = parser.parse_args()
    if not 30 <= args.seconds <= 1800:
        parser.error('seconds must be 30..1800')
    receipt = args.observer_receipt.resolve(strict=True)
    output = args.output_dir.resolve()
    if not receipt.is_relative_to(ROOT / 'logs') or not output.is_relative_to(ROOT / 'logs'):
        parser.error('paths must remain under Lynx logs')
    if output.exists():
        parser.error('output already exists')
    output.mkdir(mode=0o700)
    result = output / 'result.json'
    report = {'state': 'waiting-for-pinned-ssh', 'started_ns': time.time_ns(),
              'observer_receipt': str(receipt), 'phone_writes': False,
              'flash_performed': False, 'command': COMMAND}
    save(result, report)
    deadline = time.monotonic() + args.seconds
    while time.monotonic() < deadline:
        observed = json.loads(receipt.read_text())
        if observed.get('early_ssh_verified') is True:
            break
        if observed.get('finished_ns') and not observed.get('early_ssh_verified'):
            report.update(state='observer-finished-without-ssh', finished_ns=time.time_ns())
            save(result, report)
            return
        time.sleep(0.5)
    else:
        report.update(state='wait-deadline', finished_ns=time.time_ns())
        save(result, report)
        return
    ip = observed.get('current_probe_ip')
    if not isinstance(ip, str) or not ip:
        raise ValueError('Observer has no verified phone address')
    raw = output / 'health-stream.raw'
    err = output / 'health-stream.stderr'
    report.update(state='streaming', connected_at_ns=time.time_ns(), phone_ip=ip)
    save(result, report)
    with raw.open('wb') as stdout, err.open('wb') as stderr:
        child = subprocess.Popen(ssh_command(ip, COMMAND), stdin=subprocess.DEVNULL,
                                 stdout=stdout, stderr=stderr)
        try:
            code = child.wait(timeout=max(1, deadline - time.monotonic()))
            state = 'stream-ended'
        except subprocess.TimeoutExpired:
            child.terminate()
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
            code = child.returncode
            state = 'stream-deadline'
    report.update(state=state, exit_code=code, finished_ns=time.time_ns(),
                  stdout_bytes=raw.stat().st_size,
                  stdout_sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),
                  stderr_bytes=err.stat().st_size)
    save(result, report)
    print(json.dumps({'state': state, 'result': str(result),
                      'stdout_bytes': report['stdout_bytes']}))


if __name__ == '__main__':
    main()
