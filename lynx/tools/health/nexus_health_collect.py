#!/usr/bin/env python3
"""Local read-only portable-health snapshot collector for Nexus (D11).

Solo Dushich round-5 item D11 (Gwyn queue, note #148): run the *portable*
common checks on Nexus itself, locally and read-only, and keep the
Nexus machine section (GPU, RAM, SMART) separate — mirroring Aigel's
vitals board without touching ``aigel/``.

Guarantees (house style for agent tools):
  * **read-only**: every source is a file read or a bounded query command;
    nothing is written, no service is touched, no RF, no device action;
  * **bounded**: every subprocess has a per-command timeout and an output
    cap; readers are injectable so tests run fully offline;
  * **honest**: a reader that fails, times out, or finds no source leaves
    that fact **absent** — the evaluator then reports ``unknown``, never
    ``ok``. Nothing is fabricated.
  * concise UTF-8 JSON on stdout; no periodic job.

Known v1 gaps (documented, not fudged):
  * no ``thermal_zone*`` on this box -> the common thermal check is
    unknown; GPU temperature lives in the machine section instead;
  * the portable network check models wifi/usb only; Nexus's wired
    uplink is not modelled in portable-health/1, so the check is
    unknown by design (portable-health/2 candidate: an ``eth`` link).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "portable-health/1"
HOST = "nexus"
PROFILE = "nexus"

DEFAULT_TIMEOUT = 10          # seconds per subprocess
MAX_OUTPUT = 8192             # chars kept per subprocess stdout
REQUIRED_SERVICES = ["ollama", "gpu_monitor"]  # declared required (see doc)
SMARTCTL_CANDIDATES = ("/usr/sbin/smartctl", "/usr/bin/smartctl")
NVME_RE = re.compile(r"^nvme[0-9]+$")  # matches Path.name


# ------------------------------------------------------------------ helpers ---


def _run(cmd, timeout=DEFAULT_TIMEOUT, max_output=MAX_OUTPUT):
    """Bounded subprocess: (returncode, stdout) or None on any failure."""
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout)
    except (subprocess.SubprocessError, OSError):
        return None
    out = proc.stdout[:max_output] if proc.stdout else ""
    return proc.returncode, out


def _read_int(text: str) -> int | None:
    m = re.search(r"-?\d+", text or "")
    return int(m.group(0)) if m else None


# ------------------------------------------------------------------ readers ---


def read_thermal():
    """max_c from thermal zones (millidegrees), throttled from throttle_count."""
    zones = sorted(Path("/sys/class/thermal").glob("thermal_zone*"))
    temps = []
    for z in zones:
        try:
            milli = int((z / "temp").read_text().strip())
        except (OSError, ValueError):
            continue
        temps.append(milli / 1000.0)
    facts: dict = {}
    if temps:
        facts["max_c"] = round(max(temps), 1)
    count_file = Path("/sys/devices/system/cpu/thermal_throttle/throttle_count")
    if count_file.exists():
        try:
            if int(count_file.read_text().strip()) > 0:
                facts["throttled"] = True
        except (OSError, ValueError):
            pass
    return facts or None


def read_storage():
    """Root filesystem used_percent and free_mib."""
    try:
        usage = shutil.disk_usage("/")
    except OSError:
        return None
    if not usage.total:
        return None
    facts = {
        "used_percent": round(100.0 * usage.used / usage.total, 1),
        "free_mib": int(usage.free // (1024 * 1024)),
    }
    return facts


def read_network():
    """v1 portable network check models wifi/usb only; Nexus uplink is wired.

    Return None (fact absent -> check unknown) rather than mislabel the
    wired uplink as wifi/usb. See module docstring.
    """
    return None


def read_services(required=REQUIRED_SERVICES):
    """is-active for each declared required service (single bounded call)."""
    result = _run(["systemctl", "is-active", *required], timeout=DEFAULT_TIMEOUT)
    if result is None:
        return None
    rc, out = result
    states = out.split()
    running, failed = [], []
    for name, state in zip(required, states):
        if state == "active":
            running.append(name)
        elif state == "failed":
            failed.append(name)
    return {"required": list(required), "running": running, "failed": failed}


def read_gpu_temp():
    res = _run(["nvidia-smi", "--query-gpu=temperature.gpu",
                "--format=csv,noheader,nounits"])
    if res is None:
        return None
    rc, out = res
    if rc != 0:
        return None
    temp = _read_int(out)
    return {"temp_c": float(temp)} if temp is not None else None


def read_xid_count():
    """Genuine NVRM Xid events in the boot journal (0 is a real value)."""
    cmd = ["journalctl", "-b", "--no-pager", "-g", "NVRM: Xid"]
    for extra in ([], ["sudo", "-n"]):
        res = _run([*extra, *cmd], timeout=15)
        if res is None:
            continue
        rc, out = res
        if rc != 0:
            continue
        return {"xid_count": len([ln for ln in out.splitlines()
                                  if re.search(r"NVRM:\s*Xid", ln)])}
    return None


def read_ecc_uncorrectable():
    res = _run(["nvidia-smi", "-q", "-d", "ECC"], timeout=DEFAULT_TIMEOUT)
    if res is None or res[0] != 0:
        return None
    m = re.search(r"Uncorrectable\s*(?:Aggregate|VolTotal)\s*:\s*(\d+)", res[1])
    if not m or m.group(1) in ("N/A", "0"):
        return None
    return {"ecc_uncorrectable": int(m.group(1))}


def read_ram():
    """MemAvailable share of MemTotal from /proc/meminfo (Aigel convention)."""
    try:
        text = Path("/proc/meminfo").read_text()
    except OSError:
        return None
    fields = {}
    for line in text.splitlines():
        parts = line.split(":")
        if len(parts) == 2:
            fields[parts[0].strip()] = parts[1].strip()
    total = _read_int(fields.get("MemTotal", ""))
    avail = _read_int(fields.get("MemAvailable", ""))
    if not total or avail is None:
        return None
    return {"available_pct": round(100.0 * avail / total, 1)}


def read_smart():
    """Overall-health per NVMe controller via smartctl -H (read-only).

    Tries plain first, then passwordless sudo (``/dev/nvme*`` is root-only);
    a denied attempt costs one bounded call and leaves the fact absent.
    """
    smartctl = next((p for p in SMARTCTL_CANDIDATES if os.path.exists(p)), None)
    if smartctl is None:
        return None
    try:
        devs = sorted(p for p in Path("/dev").iterdir()
                      if NVME_RE.match(p.name))
    except OSError:
        return None
    checked, failed = 0, []
    for dev in devs[:4]:  # bounded device count
        res = _run([smartctl, "-H", str(dev)], timeout=DEFAULT_TIMEOUT)
        if res is not None and res[0] == 0:
            text = res[1]
        else:  # root-only device: one bounded passwordless-sudo retry
            res = _run(["sudo", "-n", smartctl, "-H", str(dev)],
                       timeout=DEFAULT_TIMEOUT)
            if res is None or res[0] != 0:
                continue
            text = res[1]
        checked += 1
        if re.search(r"SMART overall-health self-assessment test result:\s*FAILED",
                     text):
            failed.append(dev.name)
    if checked == 0:
        return None
    return {"checked": checked, "failed_devices": failed}


# ------------------------------------------------------------------ engine ---


def collect(readers=None) -> dict:
    """Assemble the snapshot. A failing reader leaves its facts absent."""
    readers = readers or {
        "thermal": read_thermal,
        "storage": read_storage,
        "network": read_network,
        "services": read_services,
    }
    facts: dict = {}
    for name, fn in readers.items():
        try:
            value = fn()
        except Exception:
            value = None
        if value:
            facts[name] = value

    nexus: dict = {}
    for name, fn in (("gpu", _merge_gpu), ("ram", read_ram),
                     ("smart", read_smart)):
        try:
            value = fn()
        except Exception:
            value = None
        if value:
            nexus.update(value)

    return {
        "schema": SCHEMA,
        "host": HOST,
        "profile": PROFILE,
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "collector": "nexus_health_collect/1 (D11, offline read-only)",
        "route": "local",
        "facts": facts,
        "machine": {"nexus": nexus} if nexus else {},
    }


def _merge_gpu():
    merged = {}
    gpu = read_gpu_temp()
    if gpu:
        merged.update(gpu)
    xid = read_xid_count()
    if xid:
        merged.update(xid)
    ecc = read_ecc_uncorrectable()
    if ecc:
        merged.update(ecc)
    return merged or None


# -------------------------------------------------------------------- cli ---


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Local read-only portable-health snapshot for Nexus (D11).")
    parser.add_argument("--evaluate", action="store_true",
                        help="also evaluate and print the report")
    parser.add_argument("--text", action="store_true",
                        help="with --evaluate: print the text board")
    parser.add_argument("--max-age", type=int, default=None,
                        help="stale threshold seconds for --evaluate")
    args = parser.parse_args(argv)

    snapshot = collect()
    if not args.evaluate:
        print(json.dumps(snapshot, indent=2))
        return 0

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import portable_health
    report = portable_health.evaluate(snapshot, max_age_seconds=args.max_age)
    if args.text:
        print(portable_health.format_board(report))
    else:
        print(json.dumps(report, indent=2))
    return portable_health.EXIT_BY_VERDICT[report["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
