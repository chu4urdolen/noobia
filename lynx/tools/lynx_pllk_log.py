"""Capture Lynx's fixed Fastboot preloader/LK log command; no flash or reboot."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parent.parent
FASTBOOT = ROOT / 'tools/platform-tools/fastboot'
SERIAL = '89BYAY5L4T9HFUOV'
EXPECTED_FASTBOOT = 'a686e2c7e8dc9cf4cba0cb8a2eef05f7b2bd682c925abd032fe203215d80b618'


def reconstruct(raw):
    decoded = raw.decode(errors='replace')
    if not decoded.startswith('(bootloader) '):
        return ''
    # INFO payloads may themselves contain newlines. Joining line-regex
    # matches loses those continuations; remove only inter-packet framing.
    cleaned = decoded[len('(bootloader) '):]
    cleaned = re.sub(r'\n\(bootloader\) ?', '', cleaned)
    cleaned = re.split(r'\n(?:OKAY \[|FAILED \(|Finished\. Total time:)', cleaned, maxsplit=1)[0]
    return cleaned.replace('\r\n', '\n').replace('\r', '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connect', action='store_true')
    args = parser.parse_args()
    command = [str(FASTBOOT), '-s', SERIAL, 'oem', 'dump_pllk_log']
    if not args.connect:
        print(json.dumps({'command': command, 'phone_contacted': False, 'writes_allowed': False}))
        return
    if hashlib.sha256(FASTBOOT.read_bytes()).hexdigest() != EXPECTED_FASTBOOT:
        raise ValueError('Fastboot binary changed')
    preflight = subprocess.run(['python3', str(ROOT / 'tools/lynx_fastboot_preflight.py'), '--connect'],
                               capture_output=True, text=True, timeout=120)
    if preflight.returncode:
        raise ValueError('Identity/slot preflight failed; log command not sent: ' + preflight.stdout)
    stamp = str(time.time_ns())
    output = ROOT / 'logs' / ('pllk-' + stamp)
    report = {'command': command, 'phone_contacted': True, 'writes_allowed': False,
              'preflight': json.loads(preflight.stdout), 'state': 'issued',
              'limits': ['OEM implementation is proprietary; semantics inferred from command and published protocol client.',
                         'Logs may cover only the current Fastboot entry, rather than the failed kernel boot.',
                         'Cleaned text is a reconstruction; preserve the raw output as authoritative.']}
    receipt = output.with_suffix('.json')
    receipt.write_text(json.dumps(report, indent=2) + '\n')
    try:
        process = subprocess.run(command, capture_output=True, timeout=30)
        raw = process.stdout + process.stderr
        report.update(state='returned', exit_code=process.returncode)
    except subprocess.TimeoutExpired as error:
        raw = (error.stdout or b'') + (error.stderr or b'')
        report.update(state='timeout', exit_code=None)
    output.with_suffix('.raw.txt').write_bytes(raw)
    decoded = raw.decode(errors='replace')
    pieces = re.findall(r'^\(bootloader\) ', decoded, flags=re.MULTILINE)
    cleaned = reconstruct(raw)
    output.with_suffix('.clean.txt').write_text(cleaned)
    report.update(raw_file=str(output.with_suffix('.raw.txt')), raw_bytes=len(raw),
                  raw_sha256=hashlib.sha256(raw).hexdigest(), reconstructed_bytes=len(cleaned.encode()),
                  info_fragment_count=len(pieces))
    receipt.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ('state', 'exit_code', 'raw_bytes', 'reconstructed_bytes', 'info_fragment_count')}, indent=2))
    print('Receipt:', receipt)
    if report['exit_code'] != 0:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
