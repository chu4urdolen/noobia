"""Explicitly set Linux wall time from Nexus; preserve monotonic boot identity."""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--session', type=Path)
    parser.add_argument('--sync', action='store_true')
    args = parser.parse_args()
    if not args.sync:
        print('Use --session RECEIPT --sync to set Linux wall time from Nexus; no RTC write. No phone contacted.')
        return
    if args.session is None:
        parser.error('--session required')
    epoch = int(time.time())
    command = "set -eu; echo CLOCK_BEFORE; date -u; date +%s; cat /proc/uptime /proc/sys/kernel/random/boot_id; date -u -s @" + str(epoch) + "; echo CLOCK_AFTER; date -u; date +%s; cat /proc/uptime /proc/sys/kernel/random/boot_id"
    started_ns = time.time_ns()
    result = subprocess.run([sys.executable, str(ROOT / 'tools/lynx_live_command.py'),
                             '--session', str(args.session), '--name', 'wall-clock-sync',
                             '--command', command], capture_output=True, timeout=35)
    if result.returncode:
        sys.stdout.buffer.write(result.stdout); sys.stderr.buffer.write(result.stderr)
        raise SystemExit(result.returncode)
    child = json.loads(result.stdout)
    receipt = Path(child['result'])
    raw = receipt.with_name('command.stdout').read_text()
    before = raw.split('CLOCK_BEFORE\n', 1)[1].split('CLOCK_AFTER\n', 1)[0].splitlines()
    after = raw.split('CLOCK_AFTER\n', 1)[1].splitlines()
    observed_epoch = int(after[1])
    passed = before[3] == after[3] and epoch <= observed_epoch <= int(time.time()) + 1
    report = {'passed': passed, 'requested_epoch': epoch, 'observed_epoch': observed_epoch,
              'host_started_ns': started_ns, 'host_finished_ns': time.time_ns(),
              'native_live_receipt': str(receipt), 'boot_id_unchanged': before[3] == after[3],
              'rtc_written': False, 'limits': 'One-shot wall-time setting with SSH delay; no precision synchronization claim.'}
    output = receipt.with_name('clock-analysis.json')
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': passed, 'analysis': str(output)}))
    if not passed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
