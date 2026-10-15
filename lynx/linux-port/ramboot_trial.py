"""One verified RAM-only trial. No flash, erase, reboot or slot-change commands."""
import glob
import hashlib
import json
import os
from pathlib import Path
import select
import subprocess
import termios
import time

base = Path(__file__).resolve().parent
artifacts = base / 'artifacts/busybox-first-boot'
image = artifacts / 'nord3-busybox-ramboot-candidate.img'
build = json.loads((artifacts / 'build-validation.json').read_text())
assert hashlib.sha256(image.read_bytes()).hexdigest() == build['candidate_sha256']
assert build['kernel_identical_to_stock'] and build['init_syntax_checked_by_target_busybox']
assert image.stat().st_size < 67108864
fastboot = '/noobia/lynx/tools/platform-tools/fastboot'
serial = '89BYAY5L4T9HFUOV'
report = {'image_sha256': build['candidate_sha256'], 'flash_operations_performed': 0, 'before': {}, 'ram_boot_attempted': False, 'native_boot_proven': False}
log_path = artifacts / 'ramboot-trial.log'


def log(message):
    line = time.strftime('%Y-%m-%d %H:%M:%S%z') + ' ' + message
    with log_path.open('a') as handle:
        handle.write(line + '\n')
    print(line, flush=True)


def query(name):
    result = subprocess.run([fastboot, '-s', serial, 'getvar', name], capture_output=True, text=True, timeout=10)
    output = result.stdout + result.stderr
    log(output.strip())
    assert result.returncode == 0, 'Fastboot identity query failed'
    return output


for name, expected in [('product', 'k6983v1_64'), ('unlocked', 'yes'), ('current-slot', 'a')]:
    result = query(name)
    assert name + ': ' + expected in result
    report['before'][name] = expected

baseline = set(glob.glob('/dev/ttyACM*'))
report['ram_boot_attempted'] = True
log('Sending the validated image for one temporary RAM boot; no partition commands.')
try:
    result = subprocess.run([fastboot, '-s', serial, 'boot', str(image)], capture_output=True, text=True, timeout=90)
    report['fastboot_returncode'] = result.returncode
    report['fastboot_output'] = result.stdout + result.stderr
    log(report['fastboot_output'].strip())
    if result.returncode != 0:
        report['after'] = {name: query(name) for name in ('product', 'unlocked', 'current-slot')}
    else:
        deadline = time.monotonic() + 45
        new_devices = set()
        while time.monotonic() < deadline:
            new_devices = set(glob.glob('/dev/ttyACM*')) - baseline
            if new_devices:
                break
            time.sleep(1)
        report['new_serial_devices'] = sorted(new_devices)
        if len(new_devices) == 1:
            device = next(iter(new_devices))
            try:
                fd = os.open(device, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
                try:
                    attributes = termios.tcgetattr(fd)
                    attributes[0] = 0
                    attributes[1] = 0
                    attributes[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
                    attributes[3] = 0
                    attributes[4] = attributes[5] = termios.B115200
                    termios.tcsetattr(fd, termios.TCSANOW, attributes)
                    os.write(fd, b'\nuname -a; cat /proc/1/comm; cat /run/nord3-init.log\n')
                    console = bytearray()
                    deadline = time.monotonic() + 15
                    while time.monotonic() < deadline:
                        readable, _, _ = select.select([fd], [], [], 1)
                        if readable:
                            try:
                                console.extend(os.read(fd, 65536))
                            except BlockingIOError:
                                pass
                    decoded = console.decode(errors='replace')
                    (artifacts / 'ramboot-console.txt').write_text(decoded)
                    report['native_boot_proven'] = 'NORD3_NATIVE_LINUX_PID1_OK pid=1' in decoded
                    log(decoded)
                finally:
                    os.close(fd)
            except PermissionError:
                report['console_access_error'] = 'Linux permissions block access to ' + device
                log(report['console_access_error'])
except subprocess.TimeoutExpired as error:
    report['error'] = 'Fastboot timeout; no fallback operation attempted'
    log(report['error'])
finally:
    (artifacts / 'ramboot-trial.json').write_text(json.dumps(report, indent=2) + '\n')
log('RAM-only trial complete. Native boot proven: ' + str(report['native_boot_proven']))
