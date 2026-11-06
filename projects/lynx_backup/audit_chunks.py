"""Audit gzip chunk files and their accompanying JSON receipts.

The backup process generates a series of ``*.gz`` files and a matching
``*.json`` receipt for each chunk.  The receipt contains the following
fields:

``device``
    Identifier of the source device (e.g. ``sda``).
``offset``
    The offset in the original raw image file where this chunk begins.
``raw_size``
    The exact number of raw bytes that were compressed into the gzip.
``raw_sha256``
    The SHA‑256 digest of the uncompressed data.

The verifier performs the following checks:

* Every receipt has a corresponding ``.gz`` file.
* No two receipts refer to the same offset and the ranges are non‑overlapping.
* Each gzip file can be decompressed without errors.
* The decompressed data length matches ``raw_size``.
* The SHA‑256 of the decompressed data matches ``raw_sha256``.

The module exposes :func:`verify_directory` which returns a dictionary
containing a concise summary of the audit and a list of any problems
encountered.  It also prints a human readable summary to ``stdout``.

The verifier is intentionally self‑contained and does not perform any
network or device communication – it only operates on files present in the
filesystem.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import gzip
from dataclasses import dataclass
from typing import Dict, List, Tuple

__all__ = ["verify_directory", "AuditResult"]


@dataclass
class AuditResult:
    """Result of auditing a directory of chunks.

    Attributes
    ----------
    total_chunks:
        Total number of receipt entries processed.
    total_raw_bytes:
        Sum of ``raw_size`` values from all receipts.
    errors:
        List of human‑readable error messages.
    valid:
        ``True`` if no errors were found.
    """

    total_chunks: int = 0
    total_raw_bytes: int = 0
    errors: List[str] = None
    valid: bool = True

    def __post_init__(self):
        if self.errors is None:
            self.errors = []

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.valid = False

    def __str__(self) -> str:
        lines = [f"Audit summary: {self.total_chunks} chunks, {self.total_raw_bytes} raw bytes"]
        if self.errors:
            lines.append("Errors:")
            lines.extend(f"  - {e}" for e in self.errors)
        else:
            lines.append("No errors detected.")
        return "\n".join(lines)


def _load_receipt(path: pathlib.Path) -> Dict:
    try:
        data = json.loads(path.read_text())
    except Exception as exc:  # pragma: no cover - defensive
        raise ValueError(f"Failed to parse receipt {path}: {exc}")
    required = {"device", "offset", "raw_size", "raw_sha256"}
    if not required <= data.keys():  # pragma: no cover - defensive
        missing = required - data.keys()
        raise ValueError(f"Receipt {path} missing fields: {missing}")
    return data


def _verify_chunk(gzip_path: pathlib.Path, receipt: Dict) -> Tuple[int, str]:
    """Verify a single gzip chunk.

    Returns a tuple of (raw_size, sha256_hex) of the decompressed data.
    Raises :class:`ValueError` if verification fails.
    """
    # Stream decompress to avoid loading large files entirely into memory.
    hasher = hashlib.sha256()
    total = 0
    try:
        with gzip_path.open("rb") as f_in, gzip.GzipFile(fileobj=f_in, mode="rb") as gz:
            while True:
                chunk = gz.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                hasher.update(chunk)
    except Exception as exc:  # pragma: no cover - gzip errors
        raise ValueError(f"Failed to decompress {gzip_path}: {exc}")
    if total != receipt["raw_size"]:
        raise ValueError(
            f"Size mismatch for {gzip_path}: expected {receipt['raw_size']} bytes, got {total}"
        )
    sha_hex = hasher.hexdigest()
    if sha_hex != receipt["raw_sha256"]:
        raise ValueError(
            f"SHA256 mismatch for {gzip_path}: expected {receipt['raw_sha256']}, got {sha_hex}"
        )
    return total, sha_hex


def verify_directory(dir_path: str | pathlib.Path) -> AuditResult:
    """Audit all chunk files in ``dir_path``.

    The directory must contain a set of ``*.gz`` files and matching
    ``*.json`` receipts.  Receipt files are identified by the same stem as
    their corresponding gzip file.
    """
    base = pathlib.Path(dir_path)
    if not base.is_dir():  # pragma: no cover - defensive
        raise ValueError(f"{base} is not a directory")

    # Map of offset to receipt for overlap checking.
    offsets: List[Tuple[int, int, str]] = []  # (offset, raw_size, device)
    result = AuditResult()

    # Find all receipts.
    for receipt_path in base.glob("*.json"):
        # Skip plan metadata files like sda-plan.json
        if receipt_path.stem.endswith("-plan"):
            continue
        try:
            receipt = _load_receipt(receipt_path)
        except ValueError as exc:  # pragma: no cover - defensive
            result.add_error(str(exc))
            continue
        gz_path = base / f"{receipt_path.stem}.gz"
        if not gz_path.is_file():
            result.add_error(f"Missing gzip for receipt {receipt_path.name}")
            continue
        try:
            raw_size, sha_hex = _verify_chunk(gz_path, receipt)
        except ValueError as exc:
            result.add_error(str(exc))
            continue
        # Record for overlap check
        offsets.append((receipt["offset"], receipt["raw_size"], receipt["device"]))
        result.total_chunks += 1
        result.total_raw_bytes += raw_size

    # Detect duplicate or overlapping offsets per device.
    offsets.sort(key=lambda x: (x[2], x[0]))  # sort by device then offset
    device_map: Dict[str, List[Tuple[int, int]]] = {}
    for offset, size, device in offsets:
        device_map.setdefault(device, []).append((offset, size))
    for device, segs in device_map.items():
        segs.sort(key=lambda x: x[0])
        seen_offsets = set()
        # First chunk must start at offset 0 for a complete backup
        if segs and segs[0][0] != 0:
            result.add_error(f"First chunk for device {device} starts at {segs[0][0]}, expected 0")
        for offset, size in segs:
            if offset in seen_offsets:
                result.add_error(f"Duplicate offset {offset} for device {device}")
            else:
                seen_offsets.add(offset)
        # Check gaps and overlaps within the same device.
        for i in range(1, len(segs)):
            prev_offset, prev_size = segs[i - 1]
            cur_offset, cur_size = segs[i]
            if cur_offset < prev_offset + prev_size:
                result.add_error(
                    f"Overlapping chunks: {device}@{prev_offset}..{prev_offset+prev_size} overlaps {device}@{cur_offset}"
                )
            elif cur_offset > prev_offset + prev_size:
                result.add_error(
                    f"Gap between chunks for {device}: {prev_offset+prev_size}..{cur_offset}"
                )

    # Detect stray .gz files without receipts.
    for gz_path in base.glob("*.gz"):
        if not (base / f"{gz_path.stem}.json").is_file():
            result.add_error(f"Unmatched gzip file {gz_path.name} has no receipt")

    # Print concise summary
    print(result, file=sys.stdout)
    return result


if __name__ == "__main__":  # pragma: no cover - CLI helper
    import argparse

    parser = argparse.ArgumentParser(description="Verify backup chunk directory")
    parser.add_argument("directory", help="Path to the chunk directory")
    args = parser.parse_args()
    audit = verify_directory(args.directory)
    if not audit.valid:
        sys.exit(1)
    sys.exit(0)

