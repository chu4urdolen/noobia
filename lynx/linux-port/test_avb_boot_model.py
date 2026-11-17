"""Build and run a read-only host model using the actual AOSP AVB library."""
import hashlib
import json
from pathlib import Path
import subprocess
import shutil
import time

BASE = Path(__file__).resolve().parent
SOURCE = BASE / 'sources/aosp-avb'
library = SOURCE / 'libavb'
output = BASE.parent / 'tools/avb-host'
output.mkdir(exist_ok=True)
binary = output / 'avb-boot-model'
inputs = [BASE / 'avb_boot_model.c', *sorted(library.glob('*.c')), *sorted((library / 'crypto').glob('*.c'))]
command = ['cc', '-std=c11', '-Wall', '-Wextra', '-O2', '-DAVB_COMPILATION',
           '-I', str(SOURCE), '-I', str(library / 'crypto'), *map(str, inputs), '-o', str(binary)]
build = subprocess.run(command, capture_output=True, text=True)
(output / 'build.log').write_text(build.stdout + build.stderr)
if build.returncode:
    print(build.stdout + build.stderr)
    raise SystemExit(build.returncode)
stock_dir = BASE / 'artifacts/stock-cph2493-August-eu-ota'
old = BASE / 'artifacts/busybox-August/nord3-busybox-candidate.img'
new = BASE / 'artifacts/busybox-August-avb/nord3-busybox-candidate.img'
corrected = BASE / 'artifacts/busybox-August-lz4-avb/nord3-busybox-candidate.img'
suppliers = BASE / 'artifacts/busybox-August-suppliers/nord3-busybox-candidate.img'
cases = [('stock_unlocked', stock_dir / 'boot.img', 0, 1),
         ('previous_trial_zero_tail_unlocked', old, 0, 1),
         ('previous_trial_retained_stock_tail_unlocked', old, 1, 1),
         ('footer_candidate_unlocked', new, 0, 1),
         ('footer_candidate_locked_policy_control', new, 0, 0),
         ('lz4_footer_candidate_unlocked', corrected, 0, 1),
         ('lz4_footer_candidate_locked_policy_control', corrected, 0, 0),
         ('supplier_candidate_unlocked', suppliers, 0, 1),
         ('supplier_candidate_locked_policy_control', suppliers, 0, 0)]
results = []
for name, image, tail, unlocked in cases:
    process = subprocess.run([str(binary), str(stock_dir), str(image), str(tail), str(unlocked)],
                             capture_output=True, text=True, timeout=30)
    if process.returncode != 0:
        print(process.stdout + process.stderr)
        raise ValueError('AVB model process failed: ' + name)
    result = json.loads(process.stdout)
    result.update(case=name, image_sha256=hashlib.sha256(image.read_bytes()).hexdigest(), diagnostics=process.stderr)
    results.append(result)
    print(name, result['result'], 'loaded boot partitions:', result['boot_partitions_loaded'])
checks = {value['case']: value for value in results}
assert checks['stock_unlocked']['result'] == 'OK'
assert checks['previous_trial_zero_tail_unlocked']['result'] == 'ERROR_INVALID_METADATA'
assert checks['previous_trial_zero_tail_unlocked']['boot_partitions_loaded'] == 0
assert checks['footer_candidate_unlocked']['slot_data_returned'] and checks['footer_candidate_unlocked']['boot_partitions_loaded'] == 1
assert not checks['footer_candidate_locked_policy_control']['slot_data_returned']
assert checks['lz4_footer_candidate_unlocked']['result'] == 'ERROR_VERIFICATION'
assert checks['lz4_footer_candidate_unlocked']['slot_data_returned'] and checks['lz4_footer_candidate_unlocked']['boot_partitions_loaded'] == 1
assert not checks['lz4_footer_candidate_locked_policy_control']['slot_data_returned']
assert checks['supplier_candidate_unlocked']['result'] == 'ERROR_VERIFICATION'
assert checks['supplier_candidate_unlocked']['slot_data_returned'] and checks['supplier_candidate_unlocked']['boot_partitions_loaded'] == 1
assert not checks['supplier_candidate_locked_policy_control']['slot_data_returned']
report = {'cases': results, 'source_commit': subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip(),
          'compiler_command': command, 'source_hashes': {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs},
          'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
          'phone_contacted': False, 'phone_failure_cause_confirmed': False,
          'limits': ['This runs upstream AOSP AVB, not OnePlus LK.',
                     'Model trusts the reference root key and assumes stored rollback indexes are zero.',
                     'Actual installed vbmeta/vendor_boot/DTBO and the old boot partition tail were not read back.',
                     'Only boot loading is requested; filesystem trees and physical hardware are not modeled.']}
report_path = BASE / 'docs/avb-boot-model-results.json'
if report_path.exists():
    shutil.copyfile(report_path, output / ('previous-results-' + str(time.time_ns()) + '.json'))
report_path.write_text(json.dumps(report, indent=2) + '\n')
