#!/usr/bin/env python3
"""Aigel's vitals board — the one-glance "how is Noobia" status.

Strictly read-only. Assembles, in one bounded pass:
  * the latest sample from each of the five Aigel health stores
  * the lighthouse LAN presence beacon
  * the newest gpu_monitor CSV row (and, optionally, a live nvidia-smi read)
  * recent error-level lines from the journal
  * live state that outranks a stale store sample: the Noobia Wi-Fi link
    (via `ip`), MemAvailable (via /proc/meminfo), the applied GPU power
    limit (live nvidia-smi), GPU longevity (ECC aggregates + NVIDIA Xid
    events, matched by the driver's `NVRM: Xid` pattern only), and
    per-disk SMART health (via smartctl, read-only)
and returns a compact board with an overall verdict (ok / warn / fail).
Live values drive the verdict; store values stay visible as labeled
context.

Exit codes: 0 = ok or warn, 1 = fail, 2 = most vitals unreadable.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

STORES = {
    "cpu": "/var/log/noobia/aigel/cpu_report.log",
    "net": "/var/log/noobia/aigel/net_report.log",
    "disk": "/var/log/noobia/aigel/disk_report.log",
    "mem": "/var/log/noobia/aigel/mem_report.log",
}
GPU_LOG_DIR = "/var/log/noobia_gpu"
NOOBIA_WIFI_IFACE = "wlx40a5ef5f66f1"
DEFAULT_MINUTES = 60


# ---------------------------------------------------------------- storage ---

def latest_line(path: str, tail_bytes: int = 65536) -> str | None:
    """Last non-empty line of a (possibly large) store file, or None."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return None
    try:
        with open(path, "rb") as handle:
            handle.seek(max(0, size - tail_bytes))
            data = handle.read().decode("utf-8", "replace")
    except OSError:
        return None
    lines = [line for line in data.splitlines() if line.strip()]
    return lines[-1] if lines else None


def sample_timestamp(sample: str) -> str | None:
    match = re.match(
        r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)", sample
    )
    return match.group(1) if match else None


def parse_cpu_sample(sample: str) -> dict:
    facts = {"timestamp": sample_timestamp(sample)}
    cores = [int(value) for value in re.findall(r"cpu\d+=(\d+)%", sample)]
    if cores:
        facts["cores_count"] = len(cores)
        facts["cores_avg_pct"] = round(sum(cores) / len(cores), 1)
        facts["cores_max_pct"] = max(cores)
    load = re.search(r"load average: ([\d.]+)", sample)
    if load:
        facts["load1"] = float(load.group(1))
    ram = re.search(r"MiB Mem : ([\d.]+) total, ([\d.]+) free, ([\d.]+) used", sample)
    if ram:
        total, free = float(ram.group(1)), float(ram.group(2))
        facts["ram_free_pct"] = round(100.0 * free / total, 1) if total else None
    return facts


def parse_net_sample(sample: str) -> dict:
    facts = {"timestamp": sample_timestamp(sample)}
    state = re.search(rf"{re.escape(NOOBIA_WIFI_IFACE)}:[^;]*?state (\w+)", sample)
    if state:
        facts["wifi_state"] = state.group(1)
    rtt = re.search(r"dns-8\.8\.8\.8-rtt: ([\d.]+)/[\d.]+/[\d.]+/[\d.]+ ms", sample)
    if rtt:
        facts["dns_rtt_ms"] = float(rtt.group(1))
    return facts


def parse_disk_sample(sample: str) -> dict:
    facts = {
        "timestamp": sample_timestamp(sample),
        "mounts": [],
        "max_used_pct": 0,
        "max_used_device": None,
    }
    for device, used, free in re.findall(r"(\S+): (\d+)% used \(([^)]*)\)", sample):
        if device.startswith("/dev/loop") or device == "tmpfs":
            continue  # loop/tmpfs entries are synthetic, always "full" or small
        facts["mounts"].append({"device": device, "used_pct": int(used), "free": free})
        if int(used) > facts["max_used_pct"]:
            facts["max_used_pct"] = int(used)
            facts["max_used_device"] = device
    return facts


def parse_mem_sample(sample: str) -> dict:
    facts = {"timestamp": sample_timestamp(sample)}
    ram = re.search(r"ram: (\S+) / (\S+) used \(([^)]*)\)", sample)
    if ram:
        facts["ram_used"] = ram.group(1)
        facts["ram_total"] = ram.group(2)
        free = ram.group(3).strip()
        if free.endswith(" free"):
            free = free[: -len(" free")].strip()
        facts["ram_free"] = free
    vram = re.search(r"vram: (\d+)MiB / (\d+)MiB used \(([^)]*)\)", sample)
    if vram:
        # Store format is "vram: {total}MiB / {used}MiB used" — keep the
        # board's used/total convention and label it.
        facts["vram_total_mb"] = int(vram.group(1))
        facts["vram_used_mb"] = int(vram.group(2))
    return facts


def latest_gpu_sample(log_dir: str = GPU_LOG_DIR) -> dict | None:
    """Newest row of the newest per-hour gpu_monitor CSV file."""
    try:
        files = [path for path in Path(log_dir).glob("*.csv") if path.is_file()]
    except OSError:
        return None
    if not files:
        return None
    newest = max(files, key=lambda path: path.stat().st_mtime)
    try:
        lines = [line for line in newest.read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError:
        return None
    if not lines:
        return None
    parts = lines[-1].split(",")
    if len(parts) < 6:
        return None
    try:
        return {
            "file": newest.name,
            "timestamp": parts[0],
            "power_w": float(parts[1]),
            "util_pct": float(parts[2]),
            "temp_c": float(parts[3]),
            "vram_used_mb": float(parts[4]),
            "power_limit_w": float(parts[5]) if parts[5] else None,
        }
    except ValueError:
        return None


def nvidia_smi_live(timeout: int = 5) -> dict | None:
    """One bounded live read from nvidia-smi, or None."""
    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,power.draw,temperature.gpu,utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    first = proc.stdout.strip().splitlines()
    if not first:
        return None
    bits = [part.strip() for part in first[0].split(",")]
    if len(bits) < 6:
        return None
    try:
        return {
            "name": bits[0],
            "power_w": float(bits[1]),
            "temp_c": float(bits[2]),
            "util_pct": float(bits[3]),
            "vram_used_mb": float(bits[4]),
            "vram_total_mb": float(bits[5]),
        }
    except ValueError:
        return None


def recent_errors(minutes: int = DEFAULT_MINUTES, limit: int = 8, timeout: int = 10) -> dict:
    """Bounded count + last lines of error-level journal entries in a window."""
    try:
        proc = subprocess.run(
            ["journalctl", f"--since=-{minutes}m", "-p", "err", "--no-pager", "-q"],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return {"minutes": minutes, "count": None, "lines": []}
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    return {"minutes": minutes, "count": len(lines), "lines": lines[-limit:]}


def load_policy(config_path: str | None = None) -> dict:
    """Aigel's shared config (aigel_sentinel's precedence), or {} on any problem."""
    tools_dir = str(Path(__file__).resolve().parent)
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    try:
        import aigel_sentinel

        return aigel_sentinel.load_config(config_path)
    except Exception:
        return {}


def lighthouse_beacon(timeout: float = 0.5) -> dict | None:
    """LAN presence via Aigel's own lighthouse tool (same process, imported)."""
    tools_dir = str(Path(__file__).resolve().parent)
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    try:
        import noob_lighthouse

        res = noob_lighthouse.probe_all(timeout=timeout)
    except Exception:
        return None
    return {
        "nexus_ready": res["nexus_ready"],
        "online": res["online"],
        "offline": res["offline"],
        "nodes": {
            name: {
                "ping_ok": record.get("ping_ok"),
                "rtt_ms": record.get("rtt_ms"),
                "open_ports": record.get("open_ports", []),
            }
            for name, record in res["inhabitants"].items()
        },
    }




# ------------------------------------------------------------ live reads ---

def _run_bounded(argv: list[str], timeout: int = 10) -> "subprocess.CompletedProcess | None":
    """One bounded subprocess; None when the binary is missing or times out."""
    try:
        return subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None


def live_wifi_state(timeout: int = 5) -> str | None:
    """Live link state of the Noobia Wi-Fi interface ('UP'/'DOWN'), or None.

    Reads the kernel's own flag list via `ip -o link` — no daemon, no smartd,
    fully passive.
    """
    proc = _run_bounded(["ip", "-o", "link", "show", NOOBIA_WIFI_IFACE], timeout)
    if proc is None or proc.returncode != 0 or not proc.stdout.strip():
        return None
    line = proc.stdout.strip().splitlines()[0]
    match = re.search(r"<([^>]*)>", line)
    if not match:
        return None
    flags = [flag.strip() for flag in match.group(1).split(",")]
    return "UP" if "UP" in flags else "DOWN"


def live_ram_available(meminfo_path: str = "/proc/meminfo") -> dict | None:
    """MemAvailable as a share of MemTotal, straight from /proc/meminfo.

    MemFree undercounts badly on Linux (reclaimable buff/cache is not
    'free'), so the board and the sentinel judge RAM on MemAvailable.
    """
    try:
        text = Path(meminfo_path).read_text(encoding="utf-8")
    except OSError:
        return None

    def field(name: str) -> int | None:
        match = re.search(rf"^{re.escape(name)}:\s+(\d+)\s+kB", text, re.M)
        return int(match.group(1)) if match else None

    total, available = field("MemTotal"), field("MemAvailable")
    if not total or available is None:
        return None
    return {
        "total_kb": total,
        "available_kb": available,
        "available_pct": round(100.0 * available / total, 1),
    }


def live_power_limit_w(timeout: int = 5) -> float | None:
    """The power limit actually applied to the GPU, or None (nvidia-smi live)."""
    proc = _run_bounded(
        ["nvidia-smi", "--query-gpu=power.limit", "--format=csv,noheader,nounits"],
        timeout,
    )
    if proc is None or proc.returncode != 0 or not proc.stdout.strip():
        return None
    line = proc.stdout.strip().splitlines()[0].strip()
    try:
        return float(line)
    except ValueError:
        return None


def gpu_ecc(timeout: int = 8) -> dict | None:
    """Aggregate ECC counters from `nvidia-smi -q -d ECC`, or None.

    Cards without ECC report every field as N/A (the RTX 5090 does) — that
    is reported honestly as ``available: False``, never as a fake zero.
    """
    proc = _run_bounded(["nvidia-smi", "-q", "-d", "ECC"], timeout)
    if proc is None or proc.returncode != 0:
        return None
    match = re.search(r"Aggregate\s*\n((?:\s*\S[^\n]*\n)*)", proc.stdout)
    if not match:
        return None
    block = match.group(1)

    def counter(label: str) -> int | None:
        row = re.search(label + r"\s*:\s*([0-9]+|N/A|\[N/A\])", block)
        if not row:
            return None
        token = row.group(1)
        return None if "N/A" in token else int(token)

    correctable = counter(r"Correctable")
    uncorrectable = counter(r"Uncorrectable")
    return {
        "available": correctable is not None or uncorrectable is not None,
        "correctable": correctable,
        "uncorrectable": uncorrectable,
    }


def nvidia_xid_count(timeout: int = 15) -> int | None:
    """Count genuine NVIDIA Xid events in the boot journal, or None.

    Only the driver's ``NVRM: Xid`` pattern counts. This deliberately does
    NOT match the Realtek r8169 NIC's PCI ``XID 541`` line, which a naive
    ``xid`` grep would wrongly count.
    """
    proc = _run_bounded(["journalctl", "-b", "-q", "--no-pager"], timeout)
    if proc is None:
        return None
    count = 0
    for line in proc.stdout.splitlines():
        if re.search(r"NVRM:\s*Xid", line):
            count += 1
    return count


# ----------------------------------------------------------------- SMART ---

SMARTCTL_FALLBACKS = ("/usr/sbin/smartctl", "/usr/bin/smartctl")


def _smartctl_binary() -> str | None:
    """Locate smartctl, including /usr/sbin (not on the tool's bare PATH)."""
    import shutil

    found = shutil.which("smartctl")
    if found:
        return found
    for candidate in SMARTCTL_FALLBACKS:
        if os.path.exists(candidate):
            return candidate
    return None


def _run_smartctl(argv: list[str], timeout: int = 20) -> str | None:
    """Read-only smartctl query; plain call first, `sudo -n` retry if denied."""
    binary = _smartctl_binary()
    if binary is None:
        return None
    for command in ([binary] + list(argv), ["sudo", "-n", binary] + list(argv)):
        proc = _run_bounded(command, timeout)
        if proc is not None and proc.returncode == 0:
            return proc.stdout
    return None


def parse_smart_scan(text: str) -> list[tuple[str, list[str]]]:
    """`smartctl --scan` lines -> [(device, extra-args), ...]."""
    devices = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if parts and parts[0].startswith("/dev/"):
            devices.append((parts[0], parts[1:]))
    return devices


def parse_smart_output(text: str) -> dict:
    """Parse `smartctl -H -x` output into the per-disk health facts.

    Covers NVMe log fields (spare/used/integrity errors) and, when present,
    the SATA-style attribute table (reallocated / pending sectors). Anything
    a device does not expose stays None — the board says n/a, never 0.
    """
    facts: dict = {}
    model = re.search(r"Model Number:\s*(.+?)\s*$", text, re.M)
    if model:
        facts["model"] = model.group(1).strip()
    health = re.search(r"SMART overall-health self-assessment test result:\s*(\w+)", text)
    if health:
        facts["health"] = health.group(1)
    temp = re.search(r"^Temperature:\s+(-?\d+)\s*Celsius", text, re.M)
    if temp:
        facts["temp_c"] = int(temp.group(1))
    if "temp_c" not in facts:  # SATA-style attribute table row
        row = re.search(r"^\s*\d+\s+Temperature_Celsius\s+.*?(-?\d+)\s*$", text, re.M)
        if row:
            facts["temp_c"] = int(row.group(1))
    spare = re.search(r"Available Spare:\s+(\d+)%", text)
    if spare:
        facts["nvme_available_spare_pct"] = int(spare.group(1))
    used = re.search(r"Percentage Used:\s+(\d+)%", text)
    if used:
        facts["nvme_percentage_used_pct"] = int(used.group(1))
    media = re.search(r"Media and Data Integrity Errors:\s+(\d+)", text)
    if media:
        facts["media_errors"] = int(media.group(1))
    entries = re.search(r"Error Information Log Entries:\s+(\d+)", text)
    if entries:
        facts["error_log_entries"] = int(entries.group(1))
    for key, pattern in (
        ("reallocated", r"reallocated"),
        ("pending", r"pending[ _]?sector"),
    ):
        row = re.search(
            rf"^\s*\d+\s+\S*{pattern}\S*\s+.*?(\d+)\s*$", text, re.M | re.I
        )
        if row:
            facts[key] = int(row.group(1))
    return facts


def smart_disks(timeout: int = 20) -> dict:
    """Per-disk SMART health (read-only). ``available: False`` when smartctl
    itself is unavailable or no device answers — the board says so honestly."""
    scan_text = _run_smartctl(["--scan"], timeout)
    if scan_text is None:
        return {"available": False, "reason": "smartctl not available or unreadable"}
    devices = parse_smart_scan(scan_text)
    if not devices:
        return {"available": False, "reason": "no SMART devices reported"}
    disks = []
    for device, opts in devices:
        text = _run_smartctl(["-H", "-x", *opts, device], timeout)
        if text is None:
            disks.append({"device": device, "health": None})
            continue
        parsed = parse_smart_output(text)
        parsed["device"] = device
        disks.append(parsed)
    return {"available": True, "disks": disks, "source": "smartctl"}


def _effective_wifi_state(facts: dict) -> tuple[str | None, str]:
    """(state, source): live link state first, stale store sample as fallback."""
    state = (facts.get("wifi_live") or {}).get("state")
    if state:
        return state, "live"
    stored = (facts.get("net") or {}).get("wifi_state")
    if stored:
        return stored, "store sample"
    return None, "?"


def _effective_ram_pct(facts: dict) -> tuple[float | None, str]:
    """(pct, label): MemAvailable (live) first, store's MemFree share as fallback."""
    ram_live = facts.get("ram_live") or {}
    if ram_live.get("available_pct") is not None:
        return ram_live["available_pct"], "available (live)"
    stored = (facts.get("cpu") or {}).get("ram_free_pct")
    if stored is not None:
        return stored, "free (store sample)"
    return None, "?"


# --------------------------------------------------------------- verdict ----

def derive_verdict(facts: dict) -> tuple[str, list[str]]:
    """Fold the vitals facts into one verdict with short reasons."""
    reasons: list[str] = []
    order = {"ok": 0, "warn": 1, "fail": 2}
    level = "ok"

    def bump(severity: str, text: str) -> None:
        nonlocal level
        reasons.append(text)
        if order[severity] > order[level]:
            level = severity

    beacon = facts.get("lighthouse") or {}
    if "nexus_ready" in beacon and not beacon["nexus_ready"]:
        bump("fail", "nexus_ready=false: offline " + ",".join(beacon.get("offline", [])))

    cpu = facts.get("cpu") or {}
    ram_pct, ram_label = _effective_ram_pct(facts)
    if ram_pct is not None:
        if ram_pct < 2:
            bump("fail", f"ram {ram_pct}% {ram_label} (<2%)")
        elif ram_pct < 10:
            bump("warn", f"ram {ram_pct}% {ram_label} (<10%)")
    if cpu.get("load1") is not None and cpu.get("cores_count"):
        per_core = cpu["load1"] / cpu["cores_count"]
        if per_core >= 4:
            bump("fail", f"load1 {cpu['load1']} ≈ {per_core:.1f}/core (≥4)")
        elif per_core >= 2:
            bump("warn", f"load1 {cpu['load1']} ≈ {per_core:.1f}/core (≥2)")

    disk = facts.get("disk") or {}
    if disk.get("max_used_pct") is not None:
        if disk["max_used_pct"] >= 95:
            bump("fail", f"disk {disk.get('max_used_device')} at {disk['max_used_pct']}% (≥95%)")
        elif disk["max_used_pct"] >= 90:
            bump("warn", f"disk {disk.get('max_used_device')} at {disk['max_used_pct']}% (≥90%)")

    net = facts.get("net") or {}
    wifi_state, wifi_source = _effective_wifi_state(facts)
    if wifi_state == "DOWN":
        bump("fail", f"Noobia Wi-Fi interface {NOOBIA_WIFI_IFACE} is DOWN ({wifi_source})")
    if net.get("dns_rtt_ms") is not None:
        if net["dns_rtt_ms"] > 400:
            bump("fail", f"dns 8.8.8.8 rtt {net['dns_rtt_ms']}ms (>400ms)")
        elif net["dns_rtt_ms"] > 150:
            bump("warn", f"dns 8.8.8.8 rtt {net['dns_rtt_ms']}ms (>150ms)")

    gpu = facts.get("gpu") or {}
    if gpu.get("temp_c") is not None:
        if gpu["temp_c"] >= 95:
            bump("fail", f"gpu temp {gpu['temp_c']}C (≥95C)")
        elif gpu["temp_c"] >= 85:
            bump("warn", f"gpu temp {gpu['temp_c']}C (≥85C)")

    errors = facts.get("journal_errors") or {}
    if isinstance(errors.get("count"), int) and errors["count"] >= 10:
        bump("warn", f"{errors['count']} error-level journal lines in the last {errors['minutes']} min")

    gpu_store = facts.get("gpu") or {}
    longevity = facts.get("gpu_longevity") or {}
    limit = longevity.get("power_limit_w_live", gpu_store.get("power_limit_w"))
    policy = (facts.get("policy") or {}).get("power_limit_w")
    if limit is not None and policy is not None:
        try:
            if abs(float(limit) - float(policy)) > 0.01:
                bump("warn", f"gpu power limit {limit}W differs from policy {policy}W")
        except (TypeError, ValueError):
            pass

    xid = longevity.get("xid_count")
    if isinstance(xid, int) and not isinstance(xid, bool) and xid > 0:
        bump("warn", f"{xid} NVIDIA Xid event(s) in the boot journal (NVRM: Xid)")

    ecc = longevity.get("ecc") or {}
    uncorrectable = ecc.get("uncorrectable")
    if isinstance(uncorrectable, int) and uncorrectable > 0:
        bump("fail", f"gpu ECC uncorrectable errors: {uncorrectable} (aggregate)")
    correctable = ecc.get("correctable")
    if isinstance(correctable, int) and correctable > 0:
        bump("warn", f"gpu ECC correctable errors: {correctable} (aggregate)")

    smart = facts.get("smart") or {}
    for disk in smart.get("disks") or []:
        device = disk.get("device", "disk")
        if str(disk.get("health") or "").upper() == "FAILED":
            bump("fail", f"SMART overall-health FAILED on {device} ({disk.get('model') or 'disk'})")
        for key, label in (
            ("reallocated", "reallocated sectors"),
            ("pending", "pending sectors"),
            ("media_errors", "media & data-integrity errors"),
        ):
            value = disk.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
                bump("fail", f"{label}: {value} on {device}")

    for name in ("cpu", "net", "disk", "mem", "gpu"):
        if not (facts.get(name) or {}):
            bump("warn", f"no sample readable from the {name} store")

    return level, reasons


# ---------------------------------------------------------------- board -----

def collect_facts(
    store_overrides: dict | None = None,
    gpu_log_dir: str = GPU_LOG_DIR,
    minutes: int = DEFAULT_MINUTES,
    timeout: int = 10,
    include_live_gpu: bool = True,
    include_beacon: bool = True,
    include_live: bool = True,
    include_smart: bool = True,
) -> dict:
    facts: dict = {}
    for name, path in STORES.items():
        target = (store_overrides or {}).get(name, path)
        sample = latest_line(target)
        if sample is None:
            continue
        if name == "cpu":
            facts["cpu"] = parse_cpu_sample(sample)
        elif name == "net":
            facts["net"] = parse_net_sample(sample)
        elif name == "disk":
            facts["disk"] = parse_disk_sample(sample)
        elif name == "mem":
            facts["mem"] = parse_mem_sample(sample)
    if include_beacon:
        facts["lighthouse"] = lighthouse_beacon()
    facts["gpu"] = latest_gpu_sample(gpu_log_dir)
    facts["policy"] = load_policy()
    if include_live:
        wifi_state = live_wifi_state(timeout=timeout)
        if wifi_state:
            facts["wifi_live"] = {"state": wifi_state}
        ram_live = live_ram_available()
        if ram_live:
            facts["ram_live"] = ram_live
    if include_live_gpu:
        facts["gpu_live"] = nvidia_smi_live()
        longevity: dict = {}
        limit = live_power_limit_w(timeout=timeout)
        if limit is not None:
            longevity["power_limit_w_live"] = limit
        ecc = gpu_ecc(timeout=timeout)
        if ecc is not None:
            longevity["ecc"] = ecc
        xid = nvidia_xid_count(timeout=timeout)
        if xid is not None:
            longevity["xid_count"] = xid
        if longevity:
            facts["gpu_longevity"] = longevity
    if include_smart:
        facts["smart"] = smart_disks(timeout=timeout)
    facts["journal_errors"] = recent_errors(minutes=minutes, timeout=timeout)
    facts["collected_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return facts


def format_smart_disk(disk: dict) -> str:
    # One compact per-disk SMART line (n/a, never a fake zero, for unknowns).
    bits = [disk.get("device", "?")]
    if disk.get("model"):
        bits.append(f"({disk['model']})")
    bits.append(f"health={disk.get('health') or 'n/a'}")
    bits.append(f"temp={disk['temp_c']}C" if disk.get("temp_c") is not None else "temp=n/a")
    bits.append(
        f"realloc={disk.get('reallocated') if disk.get('reallocated') is not None else 'n/a'} "
        f"pending={disk.get('pending') if disk.get('pending') is not None else 'n/a'}"
    )
    if disk.get("media_errors") is not None:
        bits.append(f"media-errors={disk['media_errors']}")
    if disk.get("nvme_available_spare_pct") is not None:
        bits.append(f"spare={disk['nvme_available_spare_pct']}%")
    if disk.get("nvme_percentage_used_pct") is not None:
        bits.append(f"used={disk['nvme_percentage_used_pct']}%")
    return " ".join(bits)


def format_board(facts: dict, verdict: str, reasons: list[str]) -> str:
    why = " (" + "; ".join(reasons) + ")" if reasons else ""
    lines = [f"[aigel-vitals] {facts.get('collected_at', 'n/a')}  verdict={verdict}{why}"]

    cpu = facts.get("cpu")
    if cpu:
        lines.append(
            f"  cpu   : cores avg {cpu.get('cores_avg_pct', '?')}% (max {cpu.get('cores_max_pct', '?')}%) "
            f"load1 {cpu.get('load1', '?')} ram-free {cpu.get('ram_free_pct', '?')}%  [{cpu.get('timestamp', '?')}]"
        )
    mem = facts.get("mem")
    if mem:
        vram_used, vram_total = mem.get("vram_used_mb"), mem.get("vram_total_mb")
        vram_bits = f"vram {vram_used}/{vram_total}MiB used"
        if vram_used and vram_total:
            vram_bits += f" ({round(100.0 * vram_used / vram_total)}%)"
        ram_live = facts.get("ram_live") or {}
        live_bits = ""
        if ram_live.get("available_pct") is not None:
            live_bits = f" | MemAvailable {ram_live['available_pct']}% (live)"
        lines.append(
            f"  mem   : ram {mem.get('ram_used', '?')}/{mem.get('ram_total', '?')} used "
            f"({mem.get('ram_free', '?')} free){live_bits} {vram_bits}"
        )
    disk = facts.get("disk")
    if disk:
        lines.append(
            f"  disk  : max {disk.get('max_used_device', '?')} {disk.get('max_used_pct', '?')}% used"
        )
    net = facts.get("net") or {}
    wifi_live = (facts.get("wifi_live") or {}).get("state")
    if wifi_live or net:
        if wifi_live:
            stored = net.get("wifi_state")
            if stored and stored != wifi_live:
                wifi_bits = f"live={wifi_live} (store said {stored} — stale sample)"
            else:
                wifi_bits = f"live={wifi_live}"
        else:
            wifi_bits = net.get("wifi_state", "?")
        lines.append(
            f"  net   : noobia-wifi {NOOBIA_WIFI_IFACE} {wifi_bits} "
            f"dns 8.8.8.8 {net.get('dns_rtt_ms', '?')}ms"
        )
    gpu = facts.get("gpu")
    if gpu:
        longevity = facts.get("gpu_longevity") or {}
        limit = longevity.get("power_limit_w_live", gpu.get("power_limit_w"))
        policy = (facts.get("policy") or {}).get("power_limit_w")
        policy_bits = ""
        if policy is not None:
            policy_bits = f" policy {policy}W"
            if limit is not None:
                try:
                    if abs(float(limit) - float(policy)) > 0.01:
                        policy_bits += " ⚠ limit≠policy"
                except (TypeError, ValueError):
                    pass
        ecc = longevity.get("ecc")
        ecc_bits = ""
        if ecc is not None:
            if not ecc.get("available"):
                ecc_bits = " ecc n/a (not available on this card)"
            else:
                ecc_bits = (
                    f" ecc agg corr={ecc.get('correctable')} uncorr={ecc.get('uncorrectable')}"
                )
        xid = longevity.get("xid_count")
        xid_bits = f" xid {xid} (since boot)" if isinstance(xid, int) else ""
        lines.append(
            f"  gpu   : {gpu.get('power_w', '?')}W util {gpu.get('util_pct', '?')}% "
            f"{gpu.get('temp_c', '?')}C vram {gpu.get('vram_used_mb', '?')}MiB "
            f"limit {limit if limit is not None else '?'}W{policy_bits}{ecc_bits}{xid_bits}"
            f"  [{gpu.get('file', '?')}]"
        )
    gpu_live = facts.get("gpu_live")
    if gpu_live:
        lines.append(
            f"  nvidia: {gpu_live.get('name', '?')} live {gpu_live.get('power_w', '?')}W "
            f"{gpu_live.get('temp_c', '?')}C util {gpu_live.get('util_pct', '?')}%"
        )
    smart = facts.get("smart") or {}
    if smart:
        if smart.get("available"):
            for disk in smart.get("disks") or []:
                lines.append("  smart : " + format_smart_disk(disk))
        else:
            lines.append(f"  smart : unavailable ({smart.get('reason', 'smartctl not readable')})")
    beacon = facts.get("lighthouse")
    if beacon:
        rtt = [f"{name}={int(beacon['nodes'][name]['rtt_ms'])}ms"
               for name in beacon.get("online", [])
               if beacon.get("nodes", {}).get(name, {}).get("rtt_ms") is not None]
        lines.append(
            f"  lan   : nexus_ready={beacon.get('nexus_ready')} online={','.join(beacon.get('online', [])) or '-'} "
            f"offline={','.join(beacon.get('offline', [])) or '-'}"
            + (f" rtt={','.join(rtt)}" if rtt else "")
        )
    errors = facts.get("journal_errors") or {}
    if errors.get("count") is not None:
        lines.append(f"  journal: {errors['count']} error-level lines in the last {errors['minutes']} min")
        for line in errors.get("lines", []):
            lines.append(f"    {line}")
    if not reasons:
        lines.append("  all quiet 🌸")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print the full JSON facts board")
    parser.add_argument("--minutes", type=int, default=DEFAULT_MINUTES, help="Journal error window (min)")
    parser.add_argument("--no-beacon", action="store_true", help="Skip the LAN beacon probe")
    parser.add_argument("--no-live-gpu", action="store_true", help="Skip the live nvidia-smi read")
    parser.add_argument("--store-dir", help="Directory holding the report stores (testing)")
    args = parser.parse_args()

    store_overrides = None
    if args.store_dir:
        store_overrides = {name: os.path.join(args.store_dir, f"{name}_report.log") for name in STORES}

    facts = collect_facts(
        store_overrides=store_overrides,
        minutes=args.minutes,
        include_live_gpu=not args.no_live_gpu,
        include_beacon=not args.no_beacon,
    )
    verdict, reasons = derive_verdict(facts)
    if args.json:
        facts["verdict"] = verdict
        facts["reasons"] = reasons
        print(json.dumps(facts, indent=2))
    else:
        print(format_board(facts, verdict, reasons))
    if verdict == "fail":
        return 1
    if all(not (facts.get(name) or {}) for name in ("cpu", "net", "disk", "mem", "gpu")):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
