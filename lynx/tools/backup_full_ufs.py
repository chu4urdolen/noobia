#!/usr/bin/env python3
"""Pull Lynx UFS LUNs read-only in verified, resumable gzip chunks.

Each remote command only reads /dev/sd{a,b,c}. The local output is private.
Use --max-chunks for a bounded first run; rerun with the same --out to resume.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import zlib

from lynx_wifi_v19_contact import ssh_command


PHONE = "192.168.100.107"
PHONE_SERIAL = "89BYAY5L4T9HFUOV"
V53_BOOT_SHA256 = "c047455271828cf9bfa90984eea121d8ede8754f6297fc06f33f1e99fb23c75e"
SIZES = {"sda": 4 * 1024 * 1024, "sdb": 4 * 1024 * 1024,
         "sdc": 255_919_652_864}
MIB = 1024 * 1024
CHUNK = 1024 * MIB


def decoded_blocks(decoder: zlib.Decompress, compressed: bytes):
    """Yield at most one MiB of raw data per block, even for sparse UFS data."""
    pending = compressed
    while pending:
        raw = decoder.decompress(pending, MIB)
        if raw:
            yield raw
        remaining = decoder.unconsumed_tail
        if remaining == pending and not raw:
            raise ValueError("gzip decoder made no progress")
        pending = remaining
    while raw := decoder.decompress(b"", MIB):
        yield raw


def remote(command: str, timeout: int = 20) -> subprocess.CompletedProcess:
    argv = ssh_command(PHONE, command)
    argv[-2:-2] = ["-p", "2222", "-T", "-o", "ServerAliveInterval=10",
                    "-o", "ServerAliveCountMax=3"]
    return subprocess.run(argv, capture_output=True, timeout=timeout, check=True)


def health() -> dict:
    return json.loads(remote("/usr/local/bin/lynx-status --assert-ready").stdout)


def verify_gzip(path: Path, expected_size: int, expected_hash: str) -> None:
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    count = 0
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(MIB):
            for raw in decoded_blocks(decoder, block):
                count += len(raw)
                if count > expected_size or decoder.unused_data:
                    raise ValueError("gzip contains excess raw or trailing data")
                digest.update(raw)
    while tail := decoder.flush(MIB):
        count += len(tail)
        digest.update(tail)
    if not decoder.eof or count != expected_size or digest.hexdigest() != expected_hash:
        raise ValueError("gzip verification failed")


def save_chunk(out: Path, device: str, offset: int, size: int) -> dict:
    """Read one chunk; publish only after remote and local verification."""
    stem = f"{device}-{offset:012d}"
    final = out / f"{stem}.gz"
    receipt = out / f"{stem}.json"
    partial = out / f"{stem}.gz.part"
    if final.exists() or receipt.exists() or partial.exists():
        raise FileExistsError(f"existing output needs review: {stem}")
    if offset % MIB or size % MIB:
        raise ValueError("chunk boundaries must be MiB-aligned")
    command = (f"set -o pipefail; dd if=/dev/{device} bs=1048576 "
               f"skip={offset // MIB} count={size // MIB} 2>/dev/null | gzip -1")
    argv = ssh_command(PHONE, command)
    argv[-2:-2] = ["-p", "2222", "-T", "-o", "ServerAliveInterval=10",
                    "-o", "ServerAliveCountMax=3"]
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    digest = hashlib.sha256()
    raw_size = compressed_size = 0
    process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        with partial.open("xb") as target:
            os.chmod(partial, 0o600)
            assert process.stdout is not None
            while block := process.stdout.read(MIB):
                target.write(block)
                compressed_size += len(block)
                for raw in decoded_blocks(decoder, block):
                    raw_size += len(raw)
                    if raw_size > size or decoder.unused_data:
                        raise ValueError("remote gzip exceeded expected chunk")
                    digest.update(raw)
            target.flush()
            os.fsync(target.fileno())
        assert process.stderr is not None
        error = process.stderr.read(4096)
        code = process.wait(timeout=45)
        while tail := decoder.flush(MIB):
            raw_size += len(tail)
            digest.update(tail)
        if code or not decoder.eof or decoder.unused_data or raw_size != size:
            raise ValueError(f"remote read/gzip failed: code={code}, raw={raw_size}/{size}, stderr={error!r}")
        raw_hash = digest.hexdigest()
        verify_gzip(partial, size, raw_hash)
        record = {"device": device, "offset": offset, "raw_size": size,
                  "compressed_size": compressed_size, "raw_sha256": raw_hash,
                  "completed_utc": datetime.now(timezone.utc).isoformat()}
        receipt_part = receipt.with_suffix(".json.part")
        receipt_part.write_text(json.dumps(record, indent=2) + "\n")
        os.chmod(receipt_part, 0o600)
        with receipt_part.open("rb") as fd:
            os.fsync(fd.fileno())
        partial.rename(final)
        receipt_part.rename(receipt)
        return record
    except BaseException:
        process.kill()
        process.wait()
        partial.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--device", choices=tuple(SIZES), required=True)
    parser.add_argument("--max-chunks", type=int, default=0,
                        help="0 means all remaining chunks")
    parser.add_argument("--min-battery", type=int, default=30)
    parser.add_argument("--resume-after-reboot", action="store_true",
                        help="allow a new boot ID only after exact device and V53 boot image checks")
    args = parser.parse_args()
    if args.max_chunks < 0 or not 10 <= args.min_battery <= 80:
        parser.error("invalid chunk or battery bound")
    out = args.out.resolve()
    if not out.is_relative_to(Path("/noobia/lynx/backups")):
        parser.error("output must be under /noobia/lynx/backups")
    out.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(out, 0o700)
    size = SIZES[args.device]
    identity = remote("cat /proc/sys/kernel/random/boot_id; "
                      f"cat /sys/class/block/{args.device}/size; "
                      "sed -n 's/.*oplusboot.serialno=\\([^ ]*\\).*/\\1/p' /proc/cmdline; "
                      "sha256sum /dev/sdc39 | cut -c1-64", timeout=30)
    boot_id, sectors, serial, boot_sha = identity.stdout.decode().splitlines()
    if int(sectors) * 512 != size:
        raise RuntimeError("unexpected UFS LUN size")
    if serial != PHONE_SERIAL or boot_sha != V53_BOOT_SHA256:
        raise RuntimeError("unexpected phone identity or V53 boot image")
    plan = out / f"{args.device}-plan.json"
    if plan.exists():
        original = json.loads(plan.read_text())
        if original["size"] != size:
            raise RuntimeError("Lynx device size changed; review before resuming")
        if original["boot_id"] != boot_id:
            if not args.resume_after_reboot:
                raise RuntimeError("Lynx boot ID changed; use reviewed --resume-after-reboot")
            events = out / f"{args.device}-resume-events.jsonl"
            known = [] if not events.exists() else [json.loads(line) for line in events.read_text().splitlines()]
            if not any(event["boot_id"] == boot_id for event in known):
                with events.open("a") as stream:
                    stream.write(json.dumps({"boot_id": boot_id,
                                             "original_boot_id": original["boot_id"],
                                             "device_serial": serial,
                                             "boot_sha256": boot_sha,
                                             "resumed_utc": datetime.now(timezone.utc).isoformat()}) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                os.chmod(events, 0o600)
    else:
        plan.write_text(json.dumps({"device": args.device, "size": size,
                                    "boot_id": boot_id, "device_serial": serial,
                                    "boot_sha256": boot_sha, "chunk_size": CHUNK,
                                    "created_utc": datetime.now(timezone.utc).isoformat()}, indent=2) + "\n")
        os.chmod(plan, 0o600)
    completed = 0
    for offset in range(0, size, CHUNK):
        length = min(CHUNK, size - offset)
        stem = f"{args.device}-{offset:012d}"
        final, receipt = out / f"{stem}.gz", out / f"{stem}.json"
        if final.exists() and receipt.exists():
            previous = json.loads(receipt.read_text())
            if previous["offset"] != offset or previous["raw_size"] != length:
                raise RuntimeError(f"receipt mismatch: {stem}")
            verify_gzip(final, length, previous["raw_sha256"])
            continue
        if final.exists() or receipt.exists():
            raise RuntimeError(f"incomplete output needs review: {stem}")
        state = health()
        battery = state["battery"]
        if (state["boot_id"] != boot_id or state["issues"]
                or battery["capacity_percent"] < args.min_battery
                or battery["temperature_mC"] >= 40_000):
            print(f"STOP health gate at {stem}: battery={battery['capacity_percent']}%, issues={state['issues']}")
            return 2
        started = time.monotonic()
        record = save_chunk(out, args.device, offset, length)
        completed += 1
        print(f"{stem}: raw {length} B, gzip {record['compressed_size']} B, "
              f"sha256 {record['raw_sha256']}, {time.monotonic()-started:.1f}s", flush=True)
        if args.max_chunks and completed >= args.max_chunks:
            break
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
