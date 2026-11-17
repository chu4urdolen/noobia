"""Compare preserved bootloader evidence; no device commands."""
import hashlib
import json
from pathlib import Path
import re

BASE = Path(__file__).resolve().parent
LOGS = BASE.parent / 'logs'
captures = []
for name in ['pllk-1791641124270903778', 'pllk-1791645230944832823']:
    path = LOGS / (name + '.clean.txt')
    text = path.read_text()
    records = []
    pattern = r'BOOT_REASON:|RAM_CONSOLE pstore_addr:|SYS_PSTORE_RAW|SYS_RAMCONSOLE_RAW|kedump: crc =|\[MBOOT_PARAMS\]|Logo entries not correct|NORD3_NATIVE_LINUX_PID1_OK|noobia-init:'
    for number, line in enumerate(text.splitlines(), 1):
        if re.search(pattern, line):
            records.append({'line': number, 'text': line})
    captures.append({'capture': name, 'cleaned_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                     'records': records, 'native_pid1_marker_present': 'NORD3_NATIVE_LINUX_PID1_OK' in text})
report = {'captures': captures, 'kernel_failure_cause_confirmed': False,
          'record_age_known': False, 'phone_contacted': False,
          'stock_restore_receipt': str(LOGS / 'boot-a-usb-device-mode-trial-1791645217241106203.json'),
          'current_recorded_boot_a': 'verified August stock boot image',
          'limits': 'Changed saved-record checksums do not identify a kernel boot or failure. Export covers current preloader/LK session.'}
restoration = json.loads(Path(report['stock_restore_receipt']).read_text())
assert restoration['mode'] == 'restore-stock' and len(restoration['operations']) == 1
assert restoration['operations'][0]['exit_code'] == 0
assert restoration['operations'][0]['command'][3:5] == ['flash', 'boot_a']
(BASE / 'docs/usb-device-mode-reset-comparison.json').write_text(json.dumps(report, indent=2) + '\n')
print('Saved comparison and confirmed stock boot_a restoration; no kernel failure cause established.')
