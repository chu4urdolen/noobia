#!/usr/bin/env python3
"""Fetch and verify the reviewed Nord 3 camera source subset."""

import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "sources/oneplus-nord3-mtkcam"
MANIFEST = SOURCE / "SOURCE.json"


def main():
    manifest = json.loads(MANIFEST.read_text())
    repository = manifest["repository"]
    commit = manifest["commit"]
    if repository != "https://github.com/OnePlusOSS/android_kernel_5.10_oneplus_mt6983":
        raise SystemExit("unexpected camera source repository")
    rows = [(manifest["path"] + "/" + item["file"], SOURCE / "cam" / item["file"], item)
            for item in manifest["files"]]
    rows += [(item["path"], SOURCE / item["local"], item)
             for item in manifest.get("extra_files", [])]
    for remote, local, item in rows:
        if local.is_file():
            data = local.read_bytes()
        else:
            url = ("https://raw.githubusercontent.com/OnePlusOSS/"
                   "android_kernel_5.10_oneplus_mt6983/" + commit + "/" + remote)
            request = urllib.request.Request(url, headers={"User-Agent": "Noobia-Lynx-port"})
            with urllib.request.urlopen(request, timeout=30) as response:
                data = response.read()
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(data)
        if len(data) != item["bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise SystemExit("camera source integrity check failed: " + remote)
        print(f"verified {remote}")


if __name__ == "__main__":
    main()
