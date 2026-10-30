#!/usr/bin/env python3
"""Inventory and bundle exact CPH2493 GNSS ELF dependencies offline."""

import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess

ROOT = Path(__file__).resolve().parent.parent
STOCK = ROOT / "linux-port/artifacts/stock-cph2493-August-eu-ota"
VENDOR = STOCK / "wifi-reference/vendor-unpacked"
REF = STOCK / "gnss-reference"
SEARCH = (VENDOR / "lib64/mt6983", VENDOR / "lib64",
          REF / "system-lib64", REF / "runtime-core/lib64/bionic")
SEEDS = {"mnld": VENDOR / "bin/mnld", "gps.default.so": VENDOR / "lib64/hw/gps.default.so"}
DYNAMIC = {"libcustom_nvram.so": VENDOR / "lib64/libcustom_nvram.so"}
LINKER = REF / "runtime-core/bin/linker64"
OUT = REF / "mnld-static-deps-bundle"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def elf(path):
    data = path.read_bytes()
    if len(data) < 20 or data[:4] != b"\x7fELF" or data[4] != 2 or struct.unpack_from("<H", data, 18)[0] != 183:
        raise ValueError("not an AArch64 ELF64 file: " + str(path))
    return data


def needed(path):
    process = subprocess.run(["readelf", "-d", str(path)], capture_output=True, text=True)
    if process.returncode:
        raise ValueError("readelf failed: " + str(path))
    return re.findall(r"\(NEEDED\).*?\[(.*?)\]", process.stdout)


def main():
    if OUT.exists():
        raise SystemExit("refuse to overwrite GNSS dependency bundle")
    queue = list(SEEDS.values())
    found = {}
    names = {}
    while queue:
        path = queue.pop(0)
        if str(path) in found:
            continue
        data = elf(path)
        found[str(path)] = {"sha256": sha(data), "bytes": len(data), "needed": needed(path)}
        for name in found[str(path)]["needed"]:
            selected = next((folder / name for folder in SEARCH if (folder / name).is_file()), None)
            if selected is None:
                raise ValueError("missing GNSS dependency: " + name)
            if name in names and names[name] != str(selected):
                raise ValueError("conflicting GNSS dependency: " + name)
            names[name] = str(selected)
            queue.append(selected)
    linker = elf(LINKER)
    config = (VENDOR / "etc/MNL_Config.xml").read_bytes()
    OUT.mkdir(mode=0o700)
    (OUT / "bin").mkdir()
    (OUT / "lib64").mkdir()
    (OUT / "etc").mkdir()
    shutil.copyfile(LINKER, OUT / "bin/linker64")
    shutil.copyfile(SEEDS["mnld"], OUT / "bin/mnld")
    (OUT / "bin/linker64").chmod(0o755)
    (OUT / "bin/mnld").chmod(0o755)
    shutil.copyfile(SEEDS["gps.default.so"], OUT / "lib64/gps.default.so")
    (OUT / "etc/MNL_Config.xml").write_bytes(config)
    for name, source in sorted(names.items()):
        shutil.copyfile(source, OUT / "lib64" / name)
    dynamic = {}
    for name, source in DYNAMIC.items():
        data = elf(source)
        extra = needed(source)
        if any(dependency not in names for dependency in extra):
            raise ValueError("dynamic GNSS library has unresolved dependency: " + name)
        shutil.copyfile(source, OUT / "lib64" / name)
        dynamic[name] = {"source": str(source), "sha256": sha(data),
                         "bytes": len(data), "needed": extra}
    manifest = {"state": "offline-static-dependencies-closed",
                "source_build": "CPH2493GDPR_11_13.1.0.561EX01_2023081414430000",
                "linker_sha256": sha(linker), "config_sha256": sha(config),
                "files": found, "library_names": names, "dynamic_libraries": dynamic,
                "total_elf_bytes": sum(item["bytes"] for item in found.values()) +
                                   sum(item["bytes"] for item in dynamic.values()) + len(linker),
                "phone_contacted": False, "partition_writes": False,
                "daemon_started": False, "runtime_compatible": "unverified"}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"state": manifest["state"], "libraries": len(names),
                      "elf_bytes": manifest["total_elf_bytes"], "bundle": str(OUT)}))


if __name__ == "__main__":
    main()
