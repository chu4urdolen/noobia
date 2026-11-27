#!/usr/bin/env python3
"""Bundle stock ccci_mdinit and its 22 required 64-bit ELF dependencies.

Packages everything into /tmp/ccci-bundle.tar.gz for staging to Lynx /run.
"""

import os
import shutil
import subprocess
import tarfile
from pathlib import Path

STOCK = Path("/noobia/lynx/linux-port/artifacts/stock-cph2493-August-eu-ota")
VENDOR = STOCK / "wifi-reference/vendor-unpacked"
REF = STOCK / "gnss-reference"

SEARCH = [
    VENDOR / "lib64/mt6983",
    VENDOR / "lib64",
    REF / "system-lib64",
    REF / "runtime-core/lib64/bionic",
    REF / "mnld-static-deps-bundle/lib64",
]

DEPS = [
    "android.system.suspend-V1-ndk.so",
    "ld-android.so",
    "libandroid_runtime_lazy.so",
    "libbase.so",
    "libbinder.so",
    "libbinder_ndk.so",
    "libc++.so",
    "libc.so",
    "libccci_util.so",
    "libcutils.so",
    "libdl.so",
    "libdl_android.so",
    "libhardware_legacy.so",
    "libhidlbase.so",
    "liblog.so",
    "libm.so",
    "libnvram.so",
    "libnvram_sec.so",
    "libstorage_otp.so",
    "libsysenv.so",
    "libutils.so",
    "libvndksupport.so",
    "liblynx_props.so",
]

OUT_DIR = Path("/tmp/ccci-bundle")
TAR_PATH = Path("/tmp/ccci-bundle.tar.gz")


def main():
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    (OUT_DIR / "bin").mkdir(parents=True)
    (OUT_DIR / "lib64").mkdir(parents=True)

    # Copy linker64 and ccci_mdinit
    shutil.copyfile(REF / "runtime-core/bin/linker64", OUT_DIR / "bin/linker64")
    (OUT_DIR / "bin/linker64").chmod(0o755)

    shutil.copyfile(VENDOR / "bin/ccci_mdinit", OUT_DIR / "bin/ccci_mdinit")
    (OUT_DIR / "bin/ccci_mdinit").chmod(0o755)

    # Copy libraries
    for dep in DEPS:
        found = False
        for s in SEARCH:
            cand = s / dep
            if cand.is_file():
                shutil.copyfile(cand, OUT_DIR / "lib64" / dep)
                (OUT_DIR / "lib64" / dep).chmod(0o755)
                found = True
                break
        if not found:
            raise FileNotFoundError(f"Missing dependency: {dep}")

    # Create tarball
    with tarfile.open(TAR_PATH, "w:gz") as tar:
        tar.add(OUT_DIR, arcname="ccci-bundle")

    print(f"Bundle created at {TAR_PATH} ({TAR_PATH.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
