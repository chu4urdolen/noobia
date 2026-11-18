#!/usr/bin/env python3
"""Aigel's dmesg scout — the "forgotten line" finder.

A bounded, strictly read-only scan of the kernel log since boot
(``journalctl -k -b``, with a ``dmesg`` fallback) that extracts and
classifies kernel complaints — OOM kills, thermal throttling, NIC link
flaps, GPU Xid/ECC events, storage errors, hardware/MCE events, USB
disconnects, watchdog/lockups, and general errors — and returns a compact
digest with the original lines and their timestamps.

Exit codes: 0 = all quiet, 1 = complaints found, 2 = kernel log unreadable.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

DEFAULT_TIMEOUT = 15
DEFAULT_LIMIT = 5
DEFAULT_MAX_SCAN_LINES = 20000

CATEGORIES: list[tuple[str, re.Pattern]] = [
    ("oom_kill", re.compile(r"out of memory|oom-kill|oom_reaper|killed process", re.I)),
    ("thermal", re.compile(r"thermal|throttl|temperature above|overheat", re.I)),
    ("nic_link", re.compile(r"nic link is (up|down)|link is not ready|carrier lost|link is down", re.I)),
    ("gpu", re.compile(r"nvrm.*\bxid\b|\bxid \(gpu|ecc error|nvidia.*(xid|error|fell off)", re.I)),
    (
        "storage",
        re.compile(
            r"ext4-fs error|xfs.*error|i/o error|buffer i/o error|blk_update_request|"
            r"nvme\d+.*(error|timeout)|ata\d+.*(error|failed)|remount.*read-only",
            re.I,
        ),
    ),
    (
        "hardware",
        re.compile(r"hardware error|machine check|\bmce\b|uncorrectable|correctable memory|ce memory|aer:|pci bus error", re.I),
    ),
    ("watchdog", re.compile(r"watchdog: bug|soft lockup|rcu.*stall|hung_task|blocked for more than", re.I)),
    ("usb", re.compile(r"usb.*disconnect|device descriptor read|usb .*reset", re.I)),
]
GENERAL = re.compile(r"\b(err|error|fail|failed|failure|critical|panic|bug|oops|exception)\b", re.I)

# Well-known benign lines that would otherwise pollute the digest.
NOISE = re.compile(
    r"registered thermal governor|loading out-of-tree module|loading nvidia unix|taints kernel|"
    r"in-kernel mce decoding|if necessary, use|report a bug|firmware bug\]: bios _osi|"
    r"failed to reserve lowmem scratch|disabling kexec handover|vga decodes changed|"
    r"nvlink core is being initialized|using host bridge windows from acpi|"
    r"registered \d+ planes with drm panic|"
    r"pci: .*report a bug",
    re.I,
)


def classify_lines(lines: list[str]) -> dict[str, list[dict]]:
    """Classify raw kernel log lines into categories (first match wins).

    Lines matching no specific category are bucketed into ``general`` when
    they contain a broad error keyword; everything else is dropped.
    """
    result: dict[str, list[dict]] = {}
    for index, line in enumerate(lines):
        text = line.strip()
        if not text or NOISE.search(text):
            continue
        category = None
        for name, pattern in CATEGORIES:
            if pattern.search(text):
                category = name
                break
        if category is None and GENERAL.search(text):
            category = "general"
        if category is None:
            continue
        result.setdefault(category, []).append({"index": index, "line": text})
    return result


def message_body(line: str) -> str:
    """The log line without its leading timestamp (short-iso token or dmesg bracket)."""
    match = re.match(r"^\d{4}-\d{2}-\d{2}T[\d:+\-]+\s+", line)
    if match:
        return line[match.end():]
    match = re.match(r"^\[\s*[\d.]+\]\s*", line)
    if match:
        return line[match.end():]
    return line


def build_digest(classified: dict[str, list[dict]], limit: int = DEFAULT_LIMIT) -> dict:
    """Collapse classified lines into a compact digest.

    Repeats are deduplicated on the message body (timestamp stripped), so the
    same complaint firing at different moments counts once with a ``×N`` and
    keeps the first occurrence's timestamp.
    """
    digest: dict[str, dict] = {}
    for category in sorted(classified):
        items = classified[category]
        unique: list[dict] = []
        for item in items:
            if unique and message_body(unique[-1]["line"]) == message_body(item["line"]):
                unique[-1]["count"] += 1
            else:
                unique.append({**item, "count": 1})
        digest[category] = {
            "count": len(items),
            "first_index": items[0]["index"],
            "last_index": items[-1]["index"],
            "examples": unique[: max(1, limit)],
        }
    return digest


def line_timestamp(line: str) -> str | None:
    """Best-effort leading timestamp of a kernel log line (short-iso or dmesg)."""
    match = re.match(r"(\d{4}-\d{2}-\d{2}T[\d:+\-]+)", line)
    if match:
        return match.group(1)
    match = re.match(r"^\[\s*([\d.]+)\]", line)
    if match:
        return "boot+" + match.group(1) + "s"
    return None


RELATIVE_SINCE_RE = re.compile(r"^\s*(\d+)\s*(s|m|h|d)\s*(?:ago)?\s*$", re.IGNORECASE)
UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_since(value: str | None) -> tuple[str | None, int | None]:
    """Split a --since argument into (absolute_string, relative_seconds).

    Relative forms like ``2h ago``, ``30m``, ``1d`` become seconds; anything
    else is treated as an absolute time string for journalctl.
    """
    if not value:
        return None, None
    match = RELATIVE_SINCE_RE.match(value)
    if match:
        return None, int(match.group(1)) * UNIT_SECONDS[match.group(2).lower()]
    return value.strip(), None


def _uptime_seconds() -> float | None:
    try:
        return float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0])
    except (OSError, ValueError, IndexError):
        return None


def _dmesg_line_boot_seconds(line: str) -> float | None:
    match = re.match(r"^\[\s*([\d.]+)\]", line)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def read_kernel_log(
    source: str,
    timeout: int = DEFAULT_TIMEOUT,
    since_absolute: str | None = None,
    since_relative_s: int | None = None,
) -> tuple[list[str], str | None]:
    """Return (bounded lines, backend) for the kernel log, or ([], None).

    Without a since-window the scan covers the current boot. With one, the
    journal backend gets ``--since`` directly; the dmesg backend (no dates)
    keeps only lines whose boot-relative stamp falls inside the window.
    """
    env = dict(os.environ)
    env["PATH"] = "/usr/sbin:/sbin:/usr/bin:/bin:" + env.get("PATH", "")
    backends = ["journal", "dmesg"] if source == "auto" else [source]
    for backend in backends:
        cmd = (
            ["journalctl", "-k", "-b", "--no-pager", "-q", "-o", "short-iso"]
            if backend == "journal"
            else ["dmesg"]
        )
        if backend == "journal":
            if since_absolute:
                cmd += ["--since", since_absolute]
            elif since_relative_s is not None:
                cmd += ["--since", f"-{since_relative_s}s"]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout, check=False, env=env
            )
        except (OSError, subprocess.SubprocessError):
            continue
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        if not lines:
            continue
        if backend == "dmesg" and since_relative_s is not None:
            uptime = _uptime_seconds()
            if uptime is not None:
                floor = max(0.0, uptime - since_relative_s)
                kept = []
                for line in lines:
                    stamp = _dmesg_line_boot_seconds(line)
                    if stamp is None or stamp >= floor:
                        kept.append(line)
                lines = kept
        if lines:
            return lines[-DEFAULT_MAX_SCAN_LINES:], backend
    return [], None


def format_board(scanned: int, backend: str | None, digest: dict, window: str | None = None) -> str:
    when = f"since boot" if window is None else f"in window '{window}'"
    if not digest:
        return (
            f"[aigel-dmesg-scout] scanned {scanned} kernel lines {when} "
            f"(backend={backend or 'none'}) — all quiet 🌸"
        )
    lines = [
        f"[aigel-dmesg-scout] scanned {scanned} kernel lines {when} (backend={backend}) — "
        f"{sum(v['count'] for v in digest.values())} classified complaints"
    ]
    for category, entry in digest.items():
        lines.append(
            f"  {category}: {entry['count']} (lines {entry['first_index'] + 1}-{entry['last_index'] + 1})"
        )
        for example in entry["examples"]:
            repeated = f"  ×{example['count']}" if example["count"] > 1 else ""
            stamp = line_timestamp(example["line"])
            if stamp and example["line"].startswith(stamp):
                lines.append(f"    {example['line']}{repeated}")
            else:
                lines.append(f"    {stamp or '        '}  {example['line']}{repeated}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print a JSON digest")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Max example lines per category")
    parser.add_argument("--source", choices=("auto", "journal", "dmesg"), default="auto")
    parser.add_argument("--since",
                        help="Start the scan at this time — absolute ('2026-11-18 02:00') "
                             "or relative ('2h ago', '30m', '1d')")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Bounded read timeout (s)")
    args = parser.parse_args()

    since_absolute, since_relative_s = parse_since(args.since)
    lines, backend = read_kernel_log(args.source, args.timeout, since_absolute, since_relative_s)
    if not lines:
        message = "[aigel-dmesg-scout] could not read the kernel log (journalctl and dmesg both failed)"
        if args.json:
            print(json.dumps({"error": "kernel log unreadable"}, indent=2))
        else:
            print(message)
        return 2

    classified = classify_lines(lines)
    digest = build_digest(classified, args.limit)
    if args.json:
        print(json.dumps(
            {
                "backend": backend,
                "scanned": len(lines),
                "complaints": sum(entry["count"] for entry in digest.values()),
                "digest": digest,
            },
            indent=2,
        ))
    else:
        print(format_board(len(lines), backend, digest, window=args.since))
    return 1 if digest else 0


if __name__ == "__main__":
    sys.exit(main())
