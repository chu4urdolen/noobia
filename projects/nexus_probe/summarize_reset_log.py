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
    # Store intermediate per‑boot aggregates
    summary: Dict[str, Dict[str, object]] = {}
    counts: Dict[str, int] = defaultdict(int)
    peaks: Dict[str, float] = defaultdict(float)
    temps: Dict[str, float] = defaultdict(float)
    over_380: Dict[str, int] = defaultdict(int)
    powers: Dict[str, list[float]] = defaultdict(list)
    first_ts: Dict[str, float] = {}
    last_ts: Dict[str, float] = {}

    # Open the file using a context manager to avoid ResourceWarnings.
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            try:
                record = json.loads(line)
            except Exception:
                continue
            boot_id = record.get("boot_id")
            t = record.get("time")
            gpu = record.get("gpu")
            if not isinstance(boot_id, str) or not isinstance(gpu, list) or len(gpu) < 2:
                continue
            try:
                temp = float(gpu[0])
                power = float(gpu[1])
            except Exception:
                continue
            # Track timestamps if present
            if isinstance(t, (int, float)):
                if boot_id not in first_ts:
                    first_ts[boot_id] = t
                last_ts[boot_id] = t
            # Update counts and aggregates
            counts[boot_id] += 1
            peaks[boot_id] = max(peaks[boot_id], power)
            temps[boot_id] = max(temps[boot_id], temp)
            if power >= 380:
                over_380[boot_id] += 1
            powers[boot_id].append(power)
            # Missing timestamps remain unknown rather than becoming None by assignment.

    for boot_id in counts:
        summary[boot_id] = {
            "sample_count": counts[boot_id],
            "peak_power": peaks[boot_id],
            "last_power": powers[boot_id][-1] if powers[boot_id] else None,
            "max_temperature": temps[boot_id],
            "samples_over_380": over_380[boot_id],
            "last_six_powers": powers[boot_id][-6:] if len(powers[boot_id]) >= 6 else powers[boot_id],
            "first_time": first_ts.get(boot_id),
            "last_time": last_ts.get(boot_id),
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

