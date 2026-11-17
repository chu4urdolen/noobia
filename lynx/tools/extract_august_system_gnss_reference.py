#!/usr/bin/env python3
"""Extract the exact August CPH2493 system image offline for GNSS dependency review."""

import hashlib
import json
from pathlib import Path
import struct
import sys
import zipfile

ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / "linux-port"
sys.path.insert(0, str(PORT))
from ota_payload import parse_header, parse_manifest, reconstruct

ARCHIVE = ROOT / "downloads/CPH2493_13.1.0.561_230814-eu-ota.zip"
OUT = PORT / "artifacts/stock-cph2493-August-eu-ota/gnss-reference"
SYSTEM_SHA = "58fb6855aed4d4df727e5359fa1427a07d2f0fcf0b1bf802d6794338155a5463"
SYSTEM_SIZE = 825_716_736


def payload_start(raw, info):
    raw.seek(info.header_offset)
    header = raw.read(30)
    if len(header) != 30 or header[:4] != b"PK\x03\x04":
        raise ValueError("ZIP local header mismatch")
    name_length, extra_length = struct.unpack_from("<HH", header, 26)
    if raw.read(name_length) != b"payload.bin":
        raise ValueError("unexpected payload member")
    return info.header_offset + 30 + name_length + extra_length


def main():
    if OUT.exists():
        raise SystemExit("refuse to overwrite GNSS reference")
    with zipfile.ZipFile(ARCHIVE) as archive, ARCHIVE.open("rb") as raw:
        info = archive.getinfo("payload.bin")
        if info.compress_type != zipfile.ZIP_STORED or info.file_size != 5_648_917_013:
            raise ValueError("OTA payload layout changed")
        start = payload_start(raw, info)
        raw.seek(start)
        manifest_size, signature_size = parse_header(raw.read(24))
        manifest = raw.read(manifest_size)
        block_size, partitions = parse_manifest(manifest)
        system = partitions["system"]
        if system["size"] != SYSTEM_SIZE or system["hash"].hex() != SYSTEM_SHA:
            raise ValueError("system partition differs from verified August OTA")
        blobs_start = start + 24 + manifest_size + signature_size

        def fetch(offset, length):
            if offset < 0 or length <= 0 or offset + length > info.file_size - (blobs_start - start):
                raise ValueError("payload blob outside archive")
            raw.seek(blobs_start + offset)
            data = raw.read(length)
            if len(data) != length:
                raise ValueError("truncated payload blob")
            return data

        image = reconstruct(system, block_size, fetch, max_size=SYSTEM_SIZE)
    digest = hashlib.sha256(image).hexdigest()
    if digest != SYSTEM_SHA:
        raise ValueError("system image checksum mismatch")
    OUT.mkdir(mode=0o700)
    (OUT / "system.img").write_bytes(image)
    (OUT / "extraction.json").write_text(json.dumps({
        "state": "exact-system-extracted-offline", "bytes": len(image),
        "sha256": digest, "source": str(ARCHIVE), "phone_contacted": False,
        "partition_writes": False}, indent=2) + "\n")
    print(json.dumps({"system_image": str(OUT / "system.img"), "sha256": digest}))


if __name__ == "__main__":
    main()
