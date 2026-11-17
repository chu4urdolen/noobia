#!/usr/bin/env python3
"""Fetch and verify the pinned Nord 3 sensor power source files."""

import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "sources/oneplus-nord3-sensor-power"
MANIFEST = SOURCE / "SOURCE.json"


def main():
    manifest = json.loads(MANIFEST.read_text())
    if (manifest["repository"] != "https://github.com/OnePlusOSS/android_kernel_5.10_oneplus_mt6983" or
            manifest["commit"] != "81ec42ad5e803be0cba619f9f7bb298db7d33d7b"):
        raise RuntimeError("unexpected source repository or commit")
    for name, row in manifest["files"].items():
        target = SOURCE / name
        if target.is_file() and len(target.read_bytes()) == row["bytes"] and hashlib.sha256(target.read_bytes()).hexdigest() == row["sha256"]:
            print("verified", name)
            continue
        request = urllib.request.Request(row["source_url"], headers={"User-Agent": "Noobia-Lynx-camera-source"})
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read()
        if len(data) != row["bytes"] or hashlib.sha256(data).hexdigest() != row["sha256"]:
            raise RuntimeError("source checksum mismatch: " + name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        print("fetched", name)


if __name__ == "__main__":
    main()
