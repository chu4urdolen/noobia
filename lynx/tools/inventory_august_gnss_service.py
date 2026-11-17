#!/usr/bin/env python3
"""Record exact August CPH2493 AIDL GNSS service ELF dependency closure."""

import hashlib
import json
from pathlib import Path

from prepare_august_gnss_bundle import VENDOR, REF, needed

ROOT = Path(__file__).resolve().parent.parent
SEEDS = (VENDOR / "bin/hw/android.hardware.gnss-service.mediatek",
         VENDOR / "lib64/hw/android.hardware.gnss-impl-mediatek.so")
SEARCH = (VENDOR / "lib64/hw", VENDOR / "lib64/mt6983", VENDOR / "lib64",
          REF / "system-lib64", REF / "runtime-core/lib64/bionic", REF)
OUT = REF / "aidl-gnss-service-inventory.json"


def main():
    queue = list(SEEDS)
    files = {}
    missing = set()
    while queue:
        path = queue.pop(0)
        if str(path) in files:
            continue
        data = path.read_bytes()
        dependencies = needed(path)
        files[str(path)] = {"sha256": hashlib.sha256(data).hexdigest(),
                            "bytes": len(data), "needed": dependencies}
        for name in dependencies:
            selected = next((folder / name for folder in SEARCH if (folder / name).is_file()), None)
            if selected is None:
                missing.add(name)
            else:
                queue.append(selected)
    result = {"source_build": "CPH2493GDPR_11_13.1.0.561EX01_2023081414430000",
              "interface": "AIDL IGnss/default", "files": files,
              "missing_dependencies": sorted(missing),
              "total_bytes": sum(item["bytes"] for item in files.values()),
              "phone_contacted": False, "daemon_started": False,
              "partition_writes": False, "position_fix": False}
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"elf_count": len(files), "total_bytes": result["total_bytes"],
                      "missing": result["missing_dependencies"], "receipt": str(OUT)}))


if __name__ == "__main__":
    main()
