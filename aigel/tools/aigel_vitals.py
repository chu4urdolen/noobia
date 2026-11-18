#!/usr/bin/env python3
"""Aigel's vitals board — the one-glance "how is Noobia" status.

Strictly read-only. Assembles, in one bounded pass:
  * the latest sample from each of the five Aigel health stores
  * the lighthouse LAN presence beacon
  * the newest gpu_monitor CSV row (and, optionally, a live nvidia-smi read)
  * recent error-level lines from the journal
and returns a compact board with an overall verdict (ok / warn / fail).

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
        facts["ram_free"] = ram.group(3)
    vram = re.search(r"vram: (\d+)MiB / (\d+)MiB used \(([^)]*)\)", sample)
    if vram:
        facts["vram_used_mb"] = int(vram.group(1))
        facts["vram_total_mb"] = int(vram.group(2))
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
    if cpu.get("ram_free_pct") is not None:
        if cpu["ram_free_pct"] < 2:
            bump("fail", f"ram free {cpu['ram_free_pct']}% (<2%)")
        elif cpu["ram_free_pct"] < 10:
            bump("warn", f"ram free {cpu['ram_free_pct']}% (<10%)")
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
    if net.get("wifi_state") == "DOWN":
        bump("fail", f"Noobia Wi-Fi interface {NOOBIA_WIFI_IFACE} is DOWN")
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
    if include_live_gpu:
        facts["gpu_live"] = nvidia_smi_live()
    facts["journal_errors"] = recent_errors(minutes=minutes, timeout=timeout)
    facts["collected_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return facts


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
        lines.append(
            f"  mem   : ram {mem.get('ram_used', '?')}/{mem.get('ram_total', '?')} used "
            f"({mem.get('ram_free', '?')} free) vram {mem.get('vram_used_mb', '?')}/{mem.get('vram_total_mb', '?')}MiB"
        )
    disk = facts.get("disk")
    if disk:
        lines.append(
            f"  disk  : max {disk.get('max_used_device', '?')} {disk.get('max_used_pct', '?')}% used"
        )
    net = facts.get("net")
    if net:
        lines.append(
            f"  net   : noobia-wifi {NOOBIA_WIFI_IFACE} {net.get('wifi_state', '?')} "
            f"dns 8.8.8.8 {net.get('dns_rtt_ms', '?')}ms"
        )
    gpu = facts.get("gpu")
    if gpu:
        lines.append(
            f"  gpu   : {gpu.get('power_w', '?')}W util {gpu.get('util_pct', '?')}% "
            f"{gpu.get('temp_c', '?')}C vram {gpu.get('vram_used_mb', '?')}MiB "
            f"limit {gpu.get('power_limit_w', '?')}W  [{gpu.get('file', '?')}]"
        )
    gpu_live = facts.get("gpu_live")
    if gpu_live:
        lines.append(
            f"  nvidia: {gpu_live.get('name', '?')} live {gpu_live.get('power_w', '?')}W "
            f"{gpu_live.get('temp_c', '?')}C util {gpu_live.get('util_pct', '?')}%"
        )
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
