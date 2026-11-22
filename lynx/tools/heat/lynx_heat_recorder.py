#!/usr/bin/env python3
"""lynx-heat-recorder: a passive profiler for what heats Lynx up.

Runs ON Lynx. Every ``--interval`` seconds (default 5) it appends one JSON
line to ``/var/log/lynx/heat/heat-<boot>.jsonl`` with:

- thermal zones (all of them, millidegrees C) and cooling device states;
- battery: capacity, signed current (mA, + = charging), voltage, gauge
  temperature, and whether a charger is attached;
- CPU: per-cluster frequency, whole-system busy %, per-core busy %;
- RAM: total / available / used;
- the top processes by CPU over the interval (pid, name, cpu %, rss);
- which lynx/noobia OpenRC services are running (pidfile-based, cheap);
- display brightness, the autonomy mode, and the guard switch state.

It OBSERVES ONLY. It never throttles, kills, reboots, or powers off
anything (Principle 10). Its own CPU use is logged in each sample
(``self_cpu_pct``) so analysis can subtract it.

Disable: touch /etc/lynx/heat-recorder.disable (the loop exits cleanly).
Output is bounded: each boot file is capped at ``--max-bytes`` (default
20 MiB) and at most ``--keep`` (default 10) boot files are kept.

Usage:
    lynx_heat_recorder.py --once           # print one sample, write nothing
    lynx_heat_recorder.py [--interval 5]   # record until SIGTERM / disable
"""

from __future__ import annotations

import argparse
import glob
import json
import os
from pathlib import Path
import signal
import sys
import time

LOG_DIR = Path(os.environ.get("LYNX_HEAT_DIR", "/var/log/lynx/heat"))
DISABLE = Path("/etc/lynx/heat-recorder.disable")
GAUGE = Path("/sys/bus/i2c/devices/7-0055/battery_snapshot")
GUARD_SWITCH = Path("/etc/lynx/power-thermal-guard.disable")
MODE_FILE = Path("/var/lib/noobia/aigel_mode.txt")
TOP_N = 8
CLK_TCK = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100

_stop = False


def _on_term(signum, frame):
    global _stop
    _stop = True


def read(path, default=None):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read().strip()
    except OSError:
        return default


def read_int(path):
    v = read(path)
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ sources
def thermal() -> dict:
    zones = {}
    for z in sorted(glob.glob("/sys/class/thermal/thermal_zone*")):
        t = read_int(z + "/temp")
        name = read(z + "/type") or os.path.basename(z)
        if t is not None:
            # Several zones can share a type name; keep them apart.
            key = name if name not in zones else f"{name}#{os.path.basename(z)[12:]}"
            zones[key] = t
    cooling = {}
    for c in sorted(glob.glob("/sys/class/thermal/cooling_device*")):
        cur = read_int(c + "/cur_state")
        if cur:  # only non-zero states, to keep lines short
            cooling[read(c + "/type") or os.path.basename(c)] = cur
    return {"zones": zones, "cooling": cooling}


def battery() -> dict:
    out: dict = {}
    snap = read(GAUGE)
    if snap:
        kv = dict(line.split("=", 1) for line in snap.splitlines() if "=" in line)
        for src, dst in (("capacity_percent", "capacity"),
                         ("gauge_current_ma_signed", "current_ma"),
                         ("pack_voltage_mv", "voltage_mv"),
                         ("temperature_millidegrees_celsius", "temp_mC")):
            try:
                out[dst] = int(kv[src])
            except (KeyError, ValueError):
                pass
    online = {}
    for ps in glob.glob("/sys/class/power_supply/*"):
        kind = read(ps + "/type")
        if kind and kind.lower() != "battery":
            v = read_int(ps + "/online")
            if v is not None:
                online[os.path.basename(ps)] = v
    out["supplies_online"] = online
    out["charger"] = any(online.values()) if online else (
        out.get("current_ma", 0) > 0 if "current_ma" in out else None)
    return out


def cpu_times() -> dict:
    """{'cpu': (busy, total), 'cpu0': ...} from /proc/stat."""
    res = {}
    for line in (read("/proc/stat") or "").splitlines():
        if not line.startswith("cpu"):
            break
        parts = line.split()
        nums = [int(x) for x in parts[1:]]
        idle = nums[3] + (nums[4] if len(nums) > 4 else 0)
        res[parts[0]] = (sum(nums) - idle, sum(nums))
    return res


def freqs() -> dict:
    out = {}
    for p in sorted(glob.glob("/sys/devices/system/cpu/cpufreq/policy*")):
        out[os.path.basename(p)] = read_int(p + "/scaling_cur_freq")
    return out


def meminfo() -> dict:
    kv = {}
    for line in (read("/proc/meminfo") or "").splitlines():
        k, _, rest = line.partition(":")
        if k in ("MemTotal", "MemAvailable"):
            kv[k] = int(rest.split()[0])
    total, avail = kv.get("MemTotal"), kv.get("MemAvailable")
    if total is None or avail is None:
        return {}
    return {"total_mb": total // 1024, "avail_mb": avail // 1024,
            "used_mb": (total - avail) // 1024}


def procs() -> dict:
    """{pid: (name, utime+stime ticks, rss_pages)} for every process."""
    out = {}
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        raw = read(f"/proc/{d}/stat")
        if not raw:
            continue
        try:
            lpar, rpar = raw.index("("), raw.rindex(")")
            name = raw[lpar + 1:rpar]
            fields = raw[rpar + 2:].split()
            ticks = int(fields[11]) + int(fields[12])
            rss = int(fields[21])
        except (ValueError, IndexError):
            continue
        cmd = (read(f"/proc/{d}/cmdline") or "").replace("\0", " ").strip()
        if cmd:
            # Python services all look like "python3": name them by script.
            for tok in cmd.split():
                if tok.endswith(".py") or "/lynx-" in tok or "/noobia" in tok:
                    name = os.path.basename(tok)
                    break
        out[int(d)] = (name[:40], ticks, rss)
    return out


def services() -> dict:
    """Running lynx/noobia OpenRC services, cheaply (no rc-status call)."""
    out = {}
    for f in glob.glob("/run/openrc/started/*"):
        n = os.path.basename(f)
        if n.startswith(("lynx", "noobia", "aigel")):
            out[n] = "started"
    for f in glob.glob("/run/openrc/starting/*") + glob.glob("/run/openrc/stopping/*"):
        n = os.path.basename(f)
        if n.startswith(("lynx", "noobia", "aigel")):
            out[n] = os.path.basename(os.path.dirname(f))
    return out


def display() -> dict:
    out = {}
    for b in glob.glob("/sys/class/backlight/*"):
        out[os.path.basename(b)] = read_int(b + "/brightness")
    return out


# ------------------------------------------------------------------ sampling
class Sampler:
    def __init__(self):
        self.prev_cpu = cpu_times()
        self.prev_procs = procs()
        self.prev_t = time.monotonic()
        self.prev_self = time.process_time()

    def sample(self) -> dict:
        now = time.monotonic()
        dt = max(now - self.prev_t, 1e-3)
        cpu = cpu_times()
        cores = {}
        for k, (busy, total) in cpu.items():
            pb, pt = self.prev_cpu.get(k, (busy, total))
            cores[k] = round(100.0 * (busy - pb) / max(total - pt, 1), 1)
        cur = procs()
        top = []
        for pid, (name, ticks, rss) in cur.items():
            prev = self.prev_procs.get(pid)
            if prev:
                pct = 100.0 * (ticks - prev[1]) / CLK_TCK / dt
                if pct >= 0.5:
                    top.append((pct, pid, name, rss))
        top.sort(reverse=True)
        self_now = time.process_time()
        rec = {
            "t": round(time.time(), 1),
            "uptime_s": int(float((read("/proc/uptime") or "0 0").split()[0])),
            "cpu_pct": cores.pop("cpu", None),
            "core_pct": cores,
            "freq_khz": freqs(),
            "load": (read("/proc/loadavg") or "").split()[:3],
            "mem": meminfo(),
            "top": [{"pid": pid, "name": name, "cpu": round(pct, 1),
                     "rss_mb": rss * 4 // 1024} for pct, pid, name, rss in top[:TOP_N]],
            "thermal": thermal(),
            "battery": battery(),
            "services": services(),
            "display": display(),
            "mode": read(MODE_FILE),
            "guards_disabled": GUARD_SWITCH.exists(),
            "self_cpu_pct": round(100.0 * (self_now - self.prev_self) / dt, 2),
        }
        self.prev_cpu, self.prev_procs, self.prev_t, self.prev_self = cpu, cur, now, self_now
        return rec


def prune(keep: int):
    files = sorted(LOG_DIR.glob("heat-*.jsonl"), key=lambda p: p.stat().st_mtime)
    for old in files[:-keep]:
        try:
            old.unlink()
        except OSError:
            pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--interval", type=float, default=5.0)
    ap.add_argument("--max-bytes", type=int, default=20 * 1024 * 1024)
    ap.add_argument("--keep", type=int, default=10)
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args(argv)

    sampler = Sampler()
    if args.once:
        time.sleep(1.0)
        print(json.dumps(sampler.sample(), separators=(",", ":")))
        return 0

    signal.signal(signal.SIGTERM, _on_term)
    signal.signal(signal.SIGINT, _on_term)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    boot = (read("/proc/sys/kernel/random/boot_id") or "unknown")[:8]
    out = LOG_DIR / f"heat-{time.strftime('%Y%m%dT%H%M%S', time.gmtime())}-{boot}.jsonl"
    prune(args.keep)
    written = 0
    while not _stop and not DISABLE.exists():
        time.sleep(args.interval)
        line = json.dumps(sampler.sample(), separators=(",", ":")) + "\n"
        if written + len(line) > args.max_bytes:
            print(f"heat-recorder: {out} reached {args.max_bytes} bytes; stopping", file=sys.stderr)
            break
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())  # survive a sudden power loss
        written += len(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
