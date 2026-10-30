#!/usr/bin/env python3
"""Phone-side passive Bluetooth file install from a verified RAM stage."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


BOOT_SHA = "9206aafb339ad66b2d942ea5795b8f476a5eaf3a148f9cdfc76be22cb83e30bf"
PROGRAMS = ("lynx-bluetoothd", "lynx-bt-hciuart",
            "lynx_bluetooth_hci_probe.py", "lynx-ble-gatt")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def command(*args):
    result = subprocess.run(args, capture_output=True, timeout=20)
    if result.returncode:
        raise RuntimeError("preflight command failed: " + args[0])
    return result.stdout.decode(errors="replace")


def main(stage):
    stage = Path(stage).resolve(strict=True)
    if not str(stage).startswith("/run/lynx-bluetooth-install-"):
        raise RuntimeError("installer accepts only the guarded RAM stage")
    if command("sha256sum", "/dev/sdc39").split()[0] != BOOT_SHA:
        raise RuntimeError("boot_a is not exact V52")
    if subprocess.run(["rc-service", "bluetooth", "status"],
                      capture_output=True, timeout=5).returncode == 0:
        raise RuntimeError("Bluetooth service must be stopped")
    manifest = json.loads((stage / "firmware-sha256.json").read_text())
    if len(manifest) != 7:
        raise RuntimeError("incomplete firmware manifest")
    for name, expected in manifest.items():
        if "/" in name or digest(stage / "firmware" / name) != expected:
            raise RuntimeError("staged firmware mismatch: " + name)
    if not (stage / "vendor/dbus_next/__init__.py").is_file():
        raise RuntimeError("D-Bus library missing")

    directories = {
        Path("/vendor/firmware"): stage / "firmware",
        Path("/usr/local/lib/lynx-bluetooth"): stage / "vendor",
    }
    files = {Path("/usr/local/bin") / name: stage / "programs" / name
             for name in PROGRAMS}
    files[Path("/usr/local/share/lynx-bluetooth/firmware-sha256.json")] = \
        stage / "firmware-sha256.json"
    files[Path("/etc/init.d/lynx-bluetooth")] = stage / "lynx-bluetooth-openrc"
    for target in (*directories, *files):
        if target.exists() or target.is_symlink():
            raise RuntimeError("target already exists: " + str(target))

    created = []
    temporaries = []
    try:
        for target, source in directories.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.parent / (".lynx-bt-new-" + target.name)
            if temporary.exists():
                raise RuntimeError("stale temporary directory: " + str(temporary))
            temporaries.append(temporary)
            shutil.copytree(source, temporary)
            os.rename(temporary, target)
            temporaries.remove(temporary)
            created.append(target)
        for target, source in files.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.parent / (".lynx-bt-new-" + target.name)
            temporaries.append(temporary)
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as sink:
                sink.write(source.read_bytes())
            os.chmod(temporary, 0o755 if target.name != "firmware-sha256.json" else 0o644)
            os.link(temporary, target)  # Fails instead of replacing an unexpected file.
            temporary.unlink()
            temporaries.remove(temporary)
            created.append(target)
        for name, expected in manifest.items():
            if digest(Path("/vendor/firmware") / name) != expected:
                raise RuntimeError("installed firmware mismatch: " + name)
        env = dict(os.environ, PYTHONPATH="/usr/local/lib/lynx-bluetooth")
        test = subprocess.run(["/usr/bin/python3", "-c", "import dbus_next"],
                              env=env, capture_output=True, timeout=5)
        if test.returncode:
            raise RuntimeError("installed D-Bus library import failed")
    except Exception:
        for temporary in reversed(temporaries):
            if temporary.is_dir():
                shutil.rmtree(temporary)
            else:
                temporary.unlink(missing_ok=True)
        for target in reversed(created):
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink(missing_ok=True)
        for directory in (Path("/usr/local/share/lynx-bluetooth"), Path("/vendor")):
            try:
                directory.rmdir()
            except OSError:
                pass
        raise
    print(json.dumps({"state": "passive-files-installed",
                      "firmware_files": len(manifest), "service_started": False,
                      "service_enabled": False, "boot_partition_writes": False}))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: install.py /run/lynx-bluetooth-install-... ")
    main(sys.argv[1])
