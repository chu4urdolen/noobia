#!/usr/bin/env python3
"""Extract verified August CPH2493 system_ext image for GNSS ABI inventory."""

import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "linux-port"))
from ota_payload import parse_header, parse_manifest, reconstruct
from extract_august_system_gnss_reference import ARCHIVE, OUT, payload_start

NAME = "system_ext"
EXPECTED_SIZE = 1_031_528_448
EXPECTED_SHA = "a0c58aa4a96d"  # Full digest is checked against the OTA manifest.


def main():
    destination = OUT / "system_ext.img"
    if destination.exists():
        raise SystemExit("refuse to overwrite exact system_ext image")
    with zipfile.ZipFile(ARCHIVE) as archive, ARCHIVE.open("rb") as raw:
        info = archive.getinfo("payload.bin")
        if info.compress_type != zipfile.ZIP_STORED or info.file_size != 5_648_917_013:
            raise ValueError("OTA payload layout changed")
        start = payload_start(raw, info)
        raw.seek(start)
        manifest_size, signature_size = parse_header(raw.read(24))
        block_size, partitions = parse_manifest(raw.read(manifest_size))
        selected = partitions[NAME]
        if selected["size"] != EXPECTED_SIZE or not selected["hash"].hex().startswith(EXPECTED_SHA):
            raise ValueError("system_ext manifest differs from August reference")
        blobs_start = start + 24 + manifest_size + signature_size

        def fetch(offset, length):
            if offset < 0 or length <= 0 or offset + length > info.file_size - (blobs_start - start):
                raise ValueError("payload blob outside archive")
            raw.seek(blobs_start + offset)
            data = raw.read(length)
            if len(data) != length:
                raise ValueError("truncated payload blob")
            return data

        image = reconstruct(selected, block_size, fetch, max_size=EXPECTED_SIZE)
    digest = hashlib.sha256(image).hexdigest()
    if digest != selected["hash"].hex():
        raise ValueError("system_ext checksum mismatch")
    destination.write_bytes(image)
    (OUT / "system_ext-extraction.json").write_text(json.dumps({
        "state": "exact-system-ext-extracted-offline", "bytes": len(image),
        "sha256": digest, "source": str(ARCHIVE), "phone_contacted": False,
        "partition_writes": False}, indent=2) + "\n")
    print(json.dumps({"image": str(destination), "sha256": digest}))


if __name__ == "__main__":
    main()
