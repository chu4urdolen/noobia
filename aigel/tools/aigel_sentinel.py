#!/usr/bin/env python3
"""Aigel's sentinel — threshold alerts over the newest vitals sample.

Strictly read-only. Gathers the newest sample from Aigel's health stores
(via aigel_vitals' parsers, same directory), compares each metric against
thresholds, and records one clear alert line per crossed threshold.
It never heals anything — it only speaks.

Live state outranks a possibly stale store sample: the Wi-Fi link is read
live from the kernel (``ip``), RAM is judged on ``MemAvailable`` (live
/proc/meminfo) rather than MemFree, and the GPU power limit comes from a
live ``nvidia-smi`` read when available. New metrics cover per-disk SMART
health (smartctl, read-only), NVIDIA Xid events (matched by the driver's
``NVRM: Xid`` pattern only — never the Realtek NIC's ``XID 541`` line),
ECC aggregate counters (honest n/a on cards without ECC), and the
power-limit-vs-policy mismatch.

Thresholds
----------
Built-in defaults can be extended or overridden by the ``thresholds`` key
of Aigel's config file (default ``/noobia/aigel/config.json``, overridable
with ``--config`` or the ``AIGEL_CONFIG`` environment variable):

    {
      "sample_interval_ms": 1000,
      "thresholds": {
        "disk_used_pct": {"direction": "high", "warn": 90, "fail": 95},
        "gpu_temp_c":    {"direction": "high", "warn": 80, "fail": 90}
      }
    }

Rule shapes (extensible):
  * numeric     {"direction": "high"|"low", "warn": N, "fail": N}
                "high" = large values are bad, "low" = small values are bad
  * boolean     {"expect": true|false, "severity": "warn"|"fail"}
  * membership  {"bad": ["DOWN", ...], "severity": "warn"|"fail"}

Where alerts go
---------------
If the log directory of the log file exists (default
``/noobia/aigel/logs/aigel.log``), alert lines are appended there;
otherwise the same lines go to standard output. ``--json`` always prints
the full structure instead.

Cooldown
--------
Each metric is reported at most once per ``--cooldown-s`` window (default
300 s), for manual *and* watch runs alike — state lives in the JSON file
given by ``--state`` (default ``/noobia/aigel/private/sentinel_state.json``).
Pass ``--no-cooldown`` to force every crossed threshold through once.

Exit codes: 0 = no alerts, 1 = one or more alerts (warn or fail),
2 = could not read any facts at all.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

DEFAULT_CONFIG = "/noobia/aigel/config.json"
DEFAULT_LOG = "/noobia/aigel/logs/aigel.log"
DEFAULT_STATE = "/noobia/aigel/private/sentinel_state.json"
DEFAULT_COOLDOWN_S = 300
DEFAULT_WATCH_INTERVAL_S = 30

# Built-in defaults; config.json "thresholds" is merged over these per metric.
DEFAULT_THRESHOLDS: dict = {
    "disk_used_pct": {"direction": "high", "warn": 90, "fail": 95},
    "ram_free_pct": {"direction": "low", "warn": 10, "fail": 2},
    "load1_per_core": {"direction": "high", "warn": 2.0, "fail": 4.0},
    "dns_rtt_ms": {"direction": "high", "warn": 150, "fail": 400},
    "gpu_temp_c": {"direction": "high", "warn": 85, "fail": 95},
    "journal_error_count": {"direction": "high", "warn": 10, "fail": 50},
    "wifi_state": {"bad": ["DOWN"], "severity": "fail"},
    "nexus_ready": {"expect": True, "severity": "fail"},
    "smart_health": {"bad": ["FAILED"], "severity": "fail"},
    "smart_reallocated_sectors": {"direction": "high", "warn": 1, "fail": 1},
    "smart_pending_sectors": {"direction": "high", "warn": 1, "fail": 1},
    "smart_media_errors": {"direction": "high", "warn": 1, "fail": 1},
    "smart_percentage_used": {"direction": "high", "warn": 80, "fail": 100},
    "nvidia_xid_count": {"direction": "high", "warn": 1, "fail": 10},
    "ecc_uncorrectable": {"direction": "high", "warn": 1, "fail": 1},
    "ecc_correctable": {"direction": "high", "warn": 100, "fail": 1000},
    "gpu_limit_policy_mismatch": {"expect": False, "severity": "warn"},
}


# ------------------------------------------------------------- thresholds ---

def load_config(path: str | None = None) -> dict:
    """Load Aigel's JSON config; missing/malformed files yield {} (not an error)."""
    candidate = path or os.environ.get("AIGEL_CONFIG") or DEFAULT_CONFIG
    try:
        data = json.loads(Path(candidate).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def merge_thresholds(config: dict | None) -> dict:
    """Per-metric merge: config "thresholds" values over DEFAULT_THRESHOLDS."""
    merged = {name: dict(rule) for name, rule in DEFAULT_THRESHOLDS.items()}
    extra = (config or {}).get("thresholds")
    if isinstance(extra, dict):
        for name, rule in extra.items():
            if not isinstance(rule, dict):
                continue
            base = dict(merged.get(name, {}))
            base.update(rule)
            merged[name] = base
    return merged


def _severity_for(value: object, rule: dict) -> str | None:
    """Return 'warn'/'fail' when value crosses rule, else None."""
    if "direction" in rule:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return None
        high = rule["direction"] == "high"
        crossed = (lambda n: value >= n) if high else (lambda n: value <= n)
        if rule.get("fail") is not None and crossed(rule["fail"]):
            return "fail"
        if rule.get("warn") is not None and crossed(rule["warn"]):
            return "warn"
        return None
    if "expect" in rule:
        if value is rule["expect"]:
            return None
        return rule.get("severity", "warn")
    if "bad" in rule:
        if str(value) in {str(entry) for entry in rule["bad"]}:
            return rule.get("severity", "warn")
        return None
    return None


def _threshold_desc(value: object, rule: dict) -> str:
    if "direction" in rule:
        return "warn {} / fail {}".format(rule.get("warn"), rule.get("fail"))
    if "expect" in rule:
        return f"expected {rule['expect']}"
    if "bad" in rule:
        return "bad " + ",".join(str(entry) for entry in rule["bad"])
    return "custom"


def _extract_metric(facts: dict, name: str) -> tuple[object, str] | None:
    """Pull (value, detail) for a named metric out of vitals facts, or None."""
    if name == "disk_used_pct":
        disk = facts.get("disk") or {}
        if disk.get("max_used_pct") is None:
            return None
        return disk["max_used_pct"], f"{disk.get('max_used_device', 'disk')} at {disk['max_used_pct']}% used"
    if name == "ram_free_pct":
        ram_live = facts.get("ram_live") or {}
        if ram_live.get("available_pct") is not None:
            return ram_live["available_pct"], "MemAvailable (live /proc/meminfo)"
        cpu = facts.get("cpu") or {}
        if cpu.get("ram_free_pct") is None:
            return None
        return cpu["ram_free_pct"], f"ram free {cpu['ram_free_pct']}% (store sample)"
    if name == "load1_per_core":
        cpu = facts.get("cpu") or {}
        if cpu.get("load1") is None or not cpu.get("cores_count"):
            return None
        per_core = round(cpu["load1"] / cpu["cores_count"], 2)
        return per_core, f"load1 {cpu['load1']} on {cpu['cores_count']} cores"
    if name == "dns_rtt_ms":
        net = facts.get("net") or {}
        if net.get("dns_rtt_ms") is None:
            return None
        return net["dns_rtt_ms"], "dns 8.8.8.8 rtt"
    if name == "gpu_temp_c":
        gpu = facts.get("gpu") or {}
        source = "gpu store"
        if gpu.get("temp_c") is None:
            gpu = facts.get("gpu_live") or {}
            source = "nvidia-smi live"
        if gpu.get("temp_c") is None:
            return None
        return gpu["temp_c"], f"gpu temp from {source}"
    if name == "journal_error_count":
        errors = facts.get("journal_errors") or {}
        if not isinstance(errors.get("count"), int):
            return None
        return errors["count"], f"error-level journal lines in the last {errors.get('minutes', '?')} min"
    if name == "wifi_state":
        live = (facts.get("wifi_live") or {}).get("state")
        if live:
            return live, "Noobia Wi-Fi interface state (live)"
        net = facts.get("net") or {}
        if net.get("wifi_state") is None:
            return None
        return net["wifi_state"], "Noobia Wi-Fi interface state (store sample)"
    if name == "nexus_ready":
        beacon = facts.get("lighthouse") or {}
        if "nexus_ready" not in beacon:
            return None
        offline = ",".join(beacon.get("offline", [])) or "none"
        return beacon["nexus_ready"], f"LAN beacon; offline: {offline}"
    if name in ("smart_health", "smart_reallocated_sectors", "smart_pending_sectors",
                "smart_media_errors", "smart_percentage_used"):
        disks = (facts.get("smart") or {}).get("disks") or []
        if not disks:
            return None
        if name == "smart_health":
            worst = "PASSED"
            for disk in disks:
                if str(disk.get("health") or "").upper() == "FAILED":
                    worst = "FAILED"
                    break
            return worst, "SMART overall-health, worst of " + str(len(disks)) + " disk(s)"
        key = {
            "smart_reallocated_sectors": "reallocated",
            "smart_pending_sectors": "pending",
            "smart_media_errors": "media_errors",
            "smart_percentage_used": "nvme_percentage_used_pct",
        }[name]
        values = [disk[key] for disk in disks
                  if isinstance(disk.get(key), (int, float)) and not isinstance(disk.get(key), bool)]
        if not values:
            return None
        return max(values), "SMART " + key + ", worst across disks"
    if name == "nvidia_xid_count":
        xid = (facts.get("gpu_longevity") or {}).get("xid_count")
        if not isinstance(xid, int) or isinstance(xid, bool):
            return None
        return xid, "NVIDIA Xid events (NVRM: Xid) since boot"
    if name in ("ecc_uncorrectable", "ecc_correctable"):
        ecc = (facts.get("gpu_longevity") or {}).get("ecc") or {}
        value = ecc.get("uncorrectable" if name == "ecc_uncorrectable" else "correctable")
        if not isinstance(value, int) or isinstance(value, bool):
            return None
        return value, "ECC aggregate errors (nvidia-smi)"
    if name == "gpu_limit_policy_mismatch":
        longevity = facts.get("gpu_longevity") or {}
        limit = longevity.get("power_limit_w_live")
        if limit is None:
            limit = (facts.get("gpu") or {}).get("power_limit_w")
        policy = (facts.get("policy") or {}).get("power_limit_w")
        if limit is None or policy is None:
            return None
        try:
            mismatch = abs(float(limit) - float(policy)) > 0.01
        except (TypeError, ValueError):
            return None
        return mismatch, f"gpu limit {limit}W vs policy {policy}W"
    return None


def evaluate(facts: dict, thresholds: dict | None = None) -> list[dict]:
    """Compare facts against thresholds; return alerts sorted fail-first.

    Each alert: ``{"severity", "metric", "value", "threshold", "detail",
    "message"}`` where ``message`` is the human line (without timestamp).
    """
    rules = thresholds if thresholds is not None else DEFAULT_THRESHOLDS
    alerts: list[dict] = []
    for name, rule in rules.items():
        if not isinstance(rule, dict):
            continue
        extracted = _extract_metric(facts, name)
        if extracted is None:
            continue
        value, detail = extracted
        severity = _severity_for(value, rule)
        if not severity:
            continue
        threshold = _threshold_desc(value, rule)
        alerts.append({
            "severity": severity,
            "metric": name,
            "value": value,
            "threshold": threshold,
            "detail": detail,
            "message": f"{name}={value} (threshold {threshold}, {detail})",
        })
    alerts.sort(key=lambda alert: 0 if alert["severity"] == "fail" else 1)
    return alerts


# --------------------------------------------------------------- recording ---

def record_alerts(alerts: list[dict], log_path: str, timestamp: str | None = None) -> tuple[list[str], bool]:
    """Format alert lines; append them to log_path if its directory exists.

    Returns ``(lines, written_to_file)``. When the log directory does not
    exist, nothing is written and the caller prints the lines instead.
    """
    timestamp = timestamp or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    lines = [f"{timestamp} ALERT [{a['severity']}] {a['message']}" for a in alerts]
    parent = os.path.dirname(log_path)
    if lines and parent and os.path.isdir(parent):
        with open(log_path, "a", encoding="utf-8") as handle:
            for line in lines:
                handle.write(line + "\n")
        return lines, True
    return lines, False


# ---------------------------------------------------------------- cooldown ---

def load_state(path: str) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_state(path: str, state: dict) -> bool:
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    except OSError:
        return False
    return True


def apply_cooldown(alerts: list[dict], state: dict, now: float, cooldown_s: float) -> tuple[list[dict], dict]:
    """Drop alerts still inside their cooldown window; return kept + new state.

    State maps metric -> last reported epoch seconds. Only kept alerts update
    the state, so a metric stays silent for ``cooldown_s`` after each report.
    ``cooldown_s <= 0`` disables suppression entirely.
    """
    if cooldown_s <= 0:
        return alerts, state
    last_seen = state.get("alerts") if isinstance(state.get("alerts"), dict) else {}
    kept: list[dict] = []
    for alert in alerts:
        last = last_seen.get(alert["metric"])
        if isinstance(last, (int, float)) and (now - last) < cooldown_s:
            continue
        kept.append(alert)
        last_seen[alert["metric"]] = now
    return kept, {"alerts": last_seen}


# ----------------------------------------------------------------- gather ---

def gather_facts(args: argparse.Namespace) -> dict:
    """Newest-sample facts via aigel_vitals (same tools directory)."""
    tools_dir = str(Path(__file__).resolve().parent)
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    import aigel_vitals

    store_overrides = None
    if args.store_dir:
        store_overrides = {
            name: os.path.join(args.store_dir, f"{name}_report.log")
            for name in aigel_vitals.STORES
        }
    return aigel_vitals.collect_facts(
        store_overrides=store_overrides,
        minutes=60,
        include_live_gpu=not args.no_live_gpu,
        include_beacon=not args.no_beacon,
    )


# ------------------------------------------------------------------- main ---

def run_once(args: argparse.Namespace, config: dict, state: dict, now: float) -> tuple[int, list[dict], dict]:
    """One sentinel pass. Returns (exit_code, reported_alerts, new_state)."""
    facts = gather_facts(args)
    alerts = evaluate(facts, merge_thresholds(config))
    if not any((facts.get(name) or {}) for name in ("cpu", "net", "disk", "mem", "gpu")):
        return 2, [], state

    cooldown_s = 0.0 if args.no_cooldown else args.cooldown_s
    suppressed = 0
    if cooldown_s > 0:
        before = len(alerts)
        alerts, state = apply_cooldown(alerts, state, now, cooldown_s)
        suppressed = before - len(alerts)

    lines, written = record_alerts(alerts, args.log)
    if alerts:
        for line in lines:
            print(line)
        if written:
            print(f"[aigel-sentinel] recorded {len(lines)} alert line(s) to {args.log}")
        print(f"[aigel-sentinel] verdict={'fail' if any(a['severity'] == 'fail' for a in alerts) else 'warn'} "
              f"alerts={len(alerts)}" + (f" suppressed_in_cooldown={suppressed}" if suppressed else ""))
    elif suppressed:
        print(f"[aigel-sentinel] thresholds still crossed but {suppressed} alert(s) in cooldown — quiet for now")
    else:
        print("[aigel-sentinel] all thresholds holding — quiet 🌸")
    if args.json:
        print(json.dumps({"alerts": alerts, "facts": facts}, indent=2, default=str))
    return (1 if alerts else 0), alerts, state


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Also print the full JSON structure")
    parser.add_argument("--config", help=f"Aigel config file (default {DEFAULT_CONFIG})")
    parser.add_argument("--log", default=DEFAULT_LOG, help=f"Alert log file (default {DEFAULT_LOG})")
    parser.add_argument("--state", default=DEFAULT_STATE, help="Cooldown state file (watch mode)")
    parser.add_argument("--watch", action="store_true", help="Keep checking every --interval seconds")
    parser.add_argument("--interval", type=float, default=DEFAULT_WATCH_INTERVAL_S,
                        help=f"Watch interval in seconds (default {DEFAULT_WATCH_INTERVAL_S})")
    parser.add_argument("--cooldown-s", type=float, default=DEFAULT_COOLDOWN_S,
                        help=f"Per-metric alert cooldown, manual and watch runs (default {DEFAULT_COOLDOWN_S}, 0 disables)")
    parser.add_argument("--no-cooldown", action="store_true",
                        help="Force every crossed threshold to be reported this run (testing / fresh investigations)")
    parser.add_argument("--max-cycles", type=int, default=0, help="Stop after N watch cycles (0 = forever)")
    parser.add_argument("--no-beacon", action="store_true", help="Skip the LAN beacon probe")
    parser.add_argument("--no-live-gpu", action="store_true", help="Skip the live nvidia-smi read")
    parser.add_argument("--store-dir", help="Directory holding the report stores (testing)")
    args = parser.parse_args()

    config = load_config(args.config)
    if not args.watch:
        state = load_state(args.state)
        code, _alerts, state = run_once(args, config, state, time.time())
        save_state(args.state, state)
        return code

    state = load_state(args.state)
    code = 0
    cycles = 0
    try:
        while True:
            cycles += 1
            code, _alerts, state = run_once(args, config, state, time.time())
            save_state(args.state, state)
            if args.max_cycles and cycles >= args.max_cycles:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    return code


if __name__ == "__main__":
    sys.exit(main())
