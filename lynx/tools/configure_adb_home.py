"""Keep this task's ADB state under rose_phone; preserve any older host files."""
from datetime import datetime
import os
from pathlib import Path
import subprocess
import time

base = Path('/noobia/lynx/tools')
target = base / 'android-user-home'
temporary = base / 'adb-tmp'
target.mkdir(exist_ok=True)
temporary.mkdir(mode=0o700, exist_ok=True)
adb = str(base / 'platform-tools/adb')
subprocess.run([adb, 'kill-server'], check=True)
cutoff = time.mktime((2026, 10, 10, 1, 12, 0, 0, 0, -1))
source = Path('/home/aria/.android')
for name in ('adbkey', 'adbkey.pub', 'adb.5037'):
    path = source / name
    if not path.is_file():
        continue
    info = path.stat()
    if info.st_mtime < cutoff:
        print('Preserved older ADB file:', name, datetime.fromtimestamp(info.st_mtime).isoformat())
        continue
    destination = target / name
    if destination.exists():
        raise RuntimeError('Destination already exists; no overwriting: ' + str(destination))
    path.rename(destination)
    print('Moved task-created ADB file into workspace:', name)
environment = os.environ.copy()
environment['ANDROID_USER_HOME'] = str(target)
environment['ADB_VENDOR_KEYS'] = str(target)
environment['TMPDIR'] = str(temporary)
subprocess.run([adb, 'devices', '-l'], env=environment, check=True)
