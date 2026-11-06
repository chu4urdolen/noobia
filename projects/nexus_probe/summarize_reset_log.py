"""Utility to summarize NVIDIA GPU reset logs.

The input is a JSON Lines file where each line is a JSON object
containing a ``boot_id`` key and a ``gpu`` key that is a list
``[temperature, power_watts, utilization, memory]``.  Lines that cannot be
parsed as JSON or that miss required keys are silently skipped.

The module exposes :func:`summarize_reset_log` which returns a mapping of
``boot_id`` to a dictionary with two keys:

* ``sample_count`` – number of successfully parsed samples for that boot.
* ``peak_power`` – the maximum power value observed for that boot.

When executed as a script, the module prints a short report to stdout.
The report format is intentionally simple so that unit tests can
capture and parse it if desired.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, Tuple


def _parse_line(line: str) -> Tuple[str, float] | None:
    """Parse a single line and return ``(boot_id, power)``.

    Returns ``None`` if the line is malformed or missing required fields.
    """
    try:
        record = json.loads(line)
    except Exception:
        return None

    # Validate required fields
    boot_id = record.get("boot_id")
    gpu = record.get("gpu")
    if not isinstance(boot_id, str) or not isinstance(gpu, list) or len(gpu) < 2:
        return None
    try:
        power = float(gpu[1])
    except Exception:
        return None
    return boot_id, power


def summarize_reset_log(path: str | Path) -> Dict[str, Dict[str, float | int]]:
    """Read *path* and return a summary per boot.

    The returned dictionary maps boot identifiers to a dictionary with
    ``sample_count`` and ``peak_power`` keys.
    """
    summary: Dict[str, Dict[str, float | int]] = {}
    counts: Dict[str, int] = defaultdict(int)
    peaks: Dict[str, float] = defaultdict(float)

    # Open the file using a context manager to avoid ResourceWarnings.
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            parsed = _parse_line(line)
            if parsed is None:
                continue
            boot_id, power = parsed
            counts[boot_id] += 1
            peaks[boot_id] = max(peaks[boot_id], power)

    for boot_id in counts:
        summary[boot_id] = {
            "sample_count": counts[boot_id],
            "peak_power": peaks[boot_id],
        }
    return summary


def _print_report(summary: Dict[str, Dict[str, float | int]]) -> None:
    """Print a human‑readable report to stdout.

    The format is: ``<boot_id> samples=<n> peak_power=<p>W`` on a separate
    line per boot.
    """
    for boot_id, data in sorted(summary.items()):
        print(
            f"{boot_id} samples={data['sample_count']} peak_power={data['peak_power']}W"
        )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python summarize_reset_log.py <jsonl_file>")
        sys.exit(1)
    report = summarize_reset_log(sys.argv[1])
    _print_report(report)

