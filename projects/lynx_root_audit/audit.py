#!/usr/bin/env python3
"""Audit the result of an ext4 growth operation.

The audit script is intentionally lightweight and relies only on the
standard library.  It reads the JSON output produced by
``/noobia/lynx/tools/grow_alpine_root.py`` (``result.json``) and verifies
the following invariants:

* The growth finished in the ``grown-and-verified`` state.
* The before/after snapshots match on the following fields:
  ``serial``, ``boot_sha256``, ``boot_id``, ``start_sector``, ``partition_sectors``, ``uuid``, ``block_size``.
* The post‑growth ``block_count`` is greater than the pre‑growth count and
  between 95 % and 100 % of the partition capacity.
* No health issues are reported in the post‑growth snapshot.

The script prints a concise JSON verdict to stdout.  The verdict contains
``status`` (``pass``/``fail``) and an optional ``reason`` field.
If the audit fails the process exits with a non‑zero status code.

The module also exposes an :func:`run_audit` function that can be used by
unit tests.
"""

from __future__ import annotations

import json
import pathlib
import sys
from dataclasses import dataclass
from typing import Dict, Any

__all__ = ["run_audit", "main"]


@dataclass
class AuditError(Exception):
    message: str


def _load_json(path: pathlib.Path) -> Dict[str, Any]:
    """Load and validate the JSON structure from *path*.

    The function performs basic sanity checks for the keys that the audit
    logic requires.  It raises :class:`AuditError` if the file is missing or
    malformed.
    """
    if not path.is_file():
        raise AuditError(f"Result file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        raise AuditError(f"Failed to parse JSON: {exc}") from exc

    # Ensure required top‑level keys exist.
    required = {"state", "before", "after"}
    if not required.issubset(data):
        missing = required - data.keys()
        raise AuditError(f"Missing required keys: {missing}")
    return data


def _compare_snapshots(before: Dict[str, Any], after: Dict[str, Any]) -> None:
    """Validate that the before/after snapshots are consistent.

    Raises :class:`AuditError` if any invariant is violated.
    """
    # Identity checks
    for field in [
        "serial",
        "boot_sha256",
        "boot_id",
        "start_sector",
        "partition_sectors",
        "uuid",
        "block_size",
    ]:
        if before.get(field) != after.get(field):
            raise AuditError(f"{field} mismatch: before={before.get(field)} after={after.get(field)}")
    # Block count and partition capacity
    pre_blocks = before["block_count"]
    post_blocks = after["block_count"]
    partition_blocks = after["partition_sectors"] // 8
    if post_blocks <= pre_blocks:
        raise AuditError("post block count not greater than pre block count")
    if not (partition_blocks * 95 // 100 <= post_blocks <= partition_blocks):
        raise AuditError("post block count not within 95-100%% of partition capacity")
    # Health check
    if after["status"].get("issues"):
        raise AuditError("post snapshot reports health issues")


def run_audit(result_path: pathlib.Path | str) -> Dict[str, str]:
    """Perform the audit and return a verdict dictionary.

    The function returns ``{"status": "pass"}`` on success or
    ``{"status": "fail", "reason": <message>}`` on failure.
    """
    path = pathlib.Path(result_path)
    try:
        data = _load_json(path)
        if data["state"] != "grown-and-verified":
            raise AuditError(f"unexpected state {data['state']}")
        _compare_snapshots(data["before"], data["after"])
        return {"status": "pass"}
    except AuditError as exc:
        return {"status": "fail", "reason": str(exc)}


def main(argv: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Audit grow_alpine_root result")
    parser.add_argument("result_path", nargs="?", default="/noobia/lynx/logs/root-grow-20261107/result.json", help="Path to result.json")
    args = parser.parse_args(argv)
    verdict = run_audit(args.result_path)
    print(json.dumps(verdict, indent=2))
    sys.exit(0 if verdict["status"] == "pass" else 1)


if __name__ == "__main__":  # pragma: no cover
    main()

