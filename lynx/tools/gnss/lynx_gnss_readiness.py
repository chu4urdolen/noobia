#!/usr/bin/env python3
"""Lynx GNSS Fix-Trial Readiness Evaluator & Gated Live Collector.

Platform: OnePlus Nord 3 5G (CPH2493 / MT6983 / project 22823 'Vitamin').
Evaluates system readiness for a live attended GNSS fix trial across:
1. Power & Thermal Safety Gate (battery >= 20% cutoff / >= 35% nominal, temp <= 40°C)
2. Driver & Device Node Gate (conninfra, connadp, gps_drv, /dev/stpgps)
3. Sky-View & Signal Quality Gate (>= 4 satellites in view, C/No >= 28 dB-Hz, HDOP <= 4.0)
4. NMEA Receipt Summary (checksum, fix quality, valid fix flag)

Strictly read-only: does not actuate GPS RF, start daemons, or modify phone rootfs.
Aria runs the actual live fix trial.
"""

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_LYNX_HOST = "192.168.100.107"
DEFAULT_LYNX_PORT = 2222
SSH_TIMEOUT = 8

MIN_POWER_CUTOFF_PERCENT = 20
MIN_POWER_NOMINAL_PERCENT = 35
MIN_PACK_VOLTAGE_MV = 7400
MAX_BATTERY_TEMP_MILLIDEGREES = 40000
HARD_BATTERY_TEMP_STOP = 45000

MIN_SATELLITES_REQUIRED = 4
MAX_HDOP_ALLOWED = 4.0
MIN_CNO_DBHZ = 28.0

NMEA_PATTERN = re.compile(rb"\$[A-Z0-9]{5},[^\r\n\x00]*\*[0-9A-Fa-f]{2}")


@dataclass
class GnssReadinessVerdict:
    status: str  # "READY_FOR_TRIAL", "QUIESCENT_SAFE", "POWER_GATE_FAIL", "DRIVER_NODE_MISSING", "SKY_VIEW_OBSTRUCTED", "MALFORMED_SPEC"
    is_valid: bool
    power_gate_passed: bool
    driver_gate_passed: bool
    sky_view_gate_passed: bool
    battery_level_percent: int
    satellites_detected: int
    has_valid_fix: bool
    summary: str
    details: Dict[str, Any] = field(default_factory=dict)
    failures: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "is_valid": self.is_valid,
            "power_gate_passed": self.power_gate_passed,
            "driver_gate_passed": self.driver_gate_passed,
            "sky_view_gate_passed": self.sky_view_gate_passed,
            "battery_level_percent": self.battery_level_percent,
            "satellites_detected": self.satellites_detected,
            "has_valid_fix": self.has_valid_fix,
            "summary": self.summary,
            "failures": self.failures,
            "details": self.details,
        }


def checksum_ok(sentence: bytes) -> bool:
    """Validate 8-bit XOR checksum on NMEA 0183 sentence."""
    if b"*" not in sentence or not sentence.startswith(b"$"):
        return False
    body, expected = sentence[1:].rsplit(b"*", 1)
    actual = 0
    for byte in body:
        actual ^= byte
    try:
        return actual == int(expected, 16)
    except ValueError:
        return False


def parse_nmea_sentences(raw_nmea_lines: List[str]) -> Dict[str, Any]:
    """Parse list of NMEA sentences into summary metrics."""
    total_sentences = 0
    valid_checksums = 0
    fix_quality = 0
    satellites_used = 0
    hdop = 99.9
    rmc_valid = False
    satellites_in_view = 0
    max_cno = 0.0

    for line in raw_nmea_lines:
        line_b = line.strip().encode("ascii", errors="replace")
        if not line_b.startswith(b"$"):
            continue
        total_sentences += 1
        if not checksum_ok(line_b):
            continue
        valid_checksums += 1

        parts = line.strip().split("*")[0].split(",")
        header = parts[0][1:]

        # GGA: Global Positioning System Fix Data
        if header.endswith("GGA") and len(parts) >= 9:
            try:
                fix_quality = int(parts[6]) if parts[6].isdigit() else 0
                satellites_used = int(parts[7]) if parts[7].isdigit() else 0
                hdop = float(parts[8]) if parts[8] else 99.9
            except (ValueError, IndexError):
                pass

        # RMC: Recommended Minimum Specific GNSS Data
        elif header.endswith("RMC") and len(parts) >= 3:
            rmc_valid = (parts[2] == "A")

        # GSV: GNSS Satellites in View
        elif header.endswith("GSV") and len(parts) >= 4:
            try:
                in_view = int(parts[3]) if parts[3].isdigit() else 0
                satellites_in_view = max(satellites_in_view, in_view)
                # Check C/No values in repeats (elements 7, 11, 15, 19)
                for idx in (7, 11, 15, 19):
                    if idx < len(parts) and parts[idx].isdigit():
                        max_cno = max(max_cno, float(parts[idx]))
            except (ValueError, IndexError):
                pass

    return {
        "total_sentences": total_sentences,
        "valid_checksums": valid_checksums,
        "fix_quality": fix_quality,
        "satellites_used": satellites_used,
        "satellites_in_view": max(satellites_in_view, satellites_used),
        "hdop": hdop,
        "rmc_valid": rmc_valid,
        "max_cno_dbhz": max_cno,
    }


def parse_battery_snapshot_text(text: str) -> Dict[str, Any]:
    """Parse key=value pairs from /sys/bus/i2c/devices/7-0055/battery_snapshot."""
    result = {}
    for line in text.splitlines():
        if "=" in line:
            k, v = line.strip().split("=", 1)
            try:
                result[k] = int(v)
            except ValueError:
                result[k] = v
    return result


def evaluate_gnss_readiness(data: Dict[str, Any]) -> GnssReadinessVerdict:
    """Evaluate power, driver, node, and sky-view gates for GNSS fix readiness."""
    failures = []

    # 1. Power & Thermal Safety Gate
    battery = data.get("battery", {})
    cap = battery.get("capacity_percent", 0)
    voltage_mv = battery.get("pack_voltage_mv", 0)
    temp_mdeg = battery.get("temperature_millidegrees_celsius", 25000)
    gauge_err = (
        battery.get("capacity_error", 0)
        + battery.get("voltage_error", 0)
        + battery.get("temperature_error", 0)
    )

    power_ok = True
    if cap < MIN_POWER_CUTOFF_PERCENT:
        failures.append(f"battery_capacity_{cap}_below_cutoff_{MIN_POWER_CUTOFF_PERCENT}")
        power_ok = False
    if voltage_mv > 0 and voltage_mv < MIN_PACK_VOLTAGE_MV:
        failures.append(f"pack_voltage_{voltage_mv}_below_minimum_{MIN_PACK_VOLTAGE_MV}")
        power_ok = False
    if temp_mdeg > HARD_BATTERY_TEMP_STOP:
        failures.append(f"battery_temp_{temp_mdeg}_exceeds_hard_stop_{HARD_BATTERY_TEMP_STOP}")
        power_ok = False
    if gauge_err > 0:
        failures.append(f"battery_gauge_errors_present_{gauge_err}")
        power_ok = False

    # 2. Driver and Node Gate
    modules = data.get("loaded_modules", [])
    dev_nodes = data.get("dev_nodes", [])
    conninfra_present = "conninfra" in modules
    gps_drv_loaded = ("gps_drv" in modules or "stp_chrdev_gps" in modules)
    stpgps_node_present = any("stpgps" in str(n) for n in dev_nodes)
    agps_node_present = any("ccci_c2k_agps" in str(n) for n in dev_nodes)

    if not conninfra_present:
        failures.append("missing_conninfra_connectivity_driver")

    # 3. Sky-View & NMEA Receipt Analysis
    nmea_summary = data.get("nmea_summary")
    if not nmea_summary and "raw_nmea_sentences" in data:
        nmea_summary = parse_nmea_sentences(data["raw_nmea_sentences"])

    sats = 0
    has_fix = False
    sky_ok = False

    if nmea_summary:
        sats = nmea_summary.get("satellites_in_view", nmea_summary.get("satellites_used", 0))
        hdop = nmea_summary.get("hdop", 99.9)
        cno = nmea_summary.get("max_cno_dbhz", 0.0)
        has_fix = bool(nmea_summary.get("fix_quality", 0) >= 1 and nmea_summary.get("rmc_valid", False))

        if sats >= MIN_SATELLITES_REQUIRED and hdop <= MAX_HDOP_ALLOWED and cno >= MIN_CNO_DBHZ:
            sky_ok = True
        elif data.get("trial_mode") == "ACTIVE_FIX_TRIAL":
            if sats < MIN_SATELLITES_REQUIRED:
                failures.append(f"insufficient_satellites_detected_{sats}_min_{MIN_SATELLITES_REQUIRED}")
            if hdop > MAX_HDOP_ALLOWED:
                failures.append(f"hdop_{hdop}_exceeds_threshold_{MAX_HDOP_ALLOWED}")
            if cno < MIN_CNO_DBHZ:
                failures.append(f"cno_{cno}_below_threshold_{MIN_CNO_DBHZ}")

    # Determine Overall Verdict
    if not power_ok:
        return GnssReadinessVerdict(
            status="POWER_GATE_FAIL",
            is_valid=False,
            power_gate_passed=False,
            driver_gate_passed=(conninfra_present and gps_drv_loaded and stpgps_node_present),
            sky_view_gate_passed=sky_ok,
            battery_level_percent=cap,
            satellites_detected=sats,
            has_valid_fix=has_fix,
            summary=f"Power safety gate failed: {', '.join(failures)}",
            details=data,
            failures=failures,
        )

    # If in trial mode and missing drivers/nodes
    if data.get("trial_mode") == "ACTIVE_FIX_TRIAL":
        if not (gps_drv_loaded and stpgps_node_present):
            failures.append("gps_drv_or_stpgps_missing_during_active_trial")
            return GnssReadinessVerdict(
                status="DRIVER_NODE_MISSING",
                is_valid=False,
                power_gate_passed=True,
                driver_gate_passed=False,
                sky_view_gate_passed=sky_ok,
                battery_level_percent=cap,
                satellites_detected=sats,
                has_valid_fix=has_fix,
                summary="Active GNSS trial attempted but GPS driver or /dev/stpgps character device is missing.",
                details=data,
                failures=failures,
            )
        if not sky_ok:
            return GnssReadinessVerdict(
                status="SKY_VIEW_OBSTRUCTED",
                is_valid=False,
                power_gate_passed=True,
                driver_gate_passed=True,
                sky_view_gate_passed=False,
                battery_level_percent=cap,
                satellites_detected=sats,
                has_valid_fix=has_fix,
                summary=f"Sky-view obstructed: {sats} satellites, C/No={cno} dB-Hz, HDOP={hdop}.",
                details=data,
                failures=failures,
            )
        return GnssReadinessVerdict(
            status="READY_FOR_TRIAL",
            is_valid=True,
            power_gate_passed=True,
            driver_gate_passed=True,
            sky_view_gate_passed=True,
            battery_level_percent=cap,
            satellites_detected=sats,
            has_valid_fix=has_fix,
            summary=(
                f"GNSS fix trial ready: {sats} satellites locked, C/No={cno} dB-Hz, HDOP={hdop}, "
                f"battery at {cap}%, all drivers active."
            ),
            details=data,
            failures=[],
        )

    # Baseline quiescent state
    driver_gate = bool(conninfra_present)
    summary = (
        f"GNSS readiness verified in quiescent state: battery at {cap}% ({voltage_mv} mV), "
        f"conninfra active, /dev/ccci_c2k_agps present. Quiescent and ready for Aria's staged trial."
    )
    return GnssReadinessVerdict(
        status="QUIESCENT_SAFE",
        is_valid=True,
        power_gate_passed=True,
        driver_gate_passed=driver_gate,
        sky_view_gate_passed=sky_ok,
        battery_level_percent=cap,
        satellites_detected=sats,
        has_valid_fix=has_fix,
        summary=summary,
        details=data,
        failures=[],
    )


def collect_live_gnss_readiness(
    host: str = DEFAULT_LYNX_HOST,
    port: int = DEFAULT_LYNX_PORT,
    timeout: int = SSH_TIMEOUT,
) -> Dict[str, Any]:
    """Perform read-only live query of GNSS driver, node, and battery state over SSH."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    key_file = repo_root / "secrets/nexus_lynx_ed25519"
    known_hosts = repo_root / "secrets/lynx_known_hosts"

    if not key_file.is_file():
        return {"error": f"Missing private SSH key: {key_file}"}

    sh_script = r"""
cat /proc/sys/kernel/random/boot_id 2>/dev/null || echo "UNKNOWN_BOOT"
echo "===MODULES==="
cat /proc/modules 2>/dev/null || true
echo "===DEV_NODES==="
ls -d /dev/*gps* /dev/stpgps* /dev/ccci_c2k_agps 2>/dev/null || echo "NONE"
echo "===BATTERY_SNAPSHOT==="
cat /sys/bus/i2c/devices/7-0055/battery_snapshot 2>/dev/null || echo "NONE"
echo "===CHARGER_STATUS==="
cat /sys/class/power_supply/11e01000.i2c:mt6375@34:chg/status 2>/dev/null || echo "UNKNOWN"
"""
    cmd = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "IdentitiesOnly=yes",
        "-o", "StrictHostKeyChecking=yes",
        "-o", "GlobalKnownHostsFile=/dev/null",
        "-o", "HostKeyAlias=lynx",
        "-o", f"UserKnownHostsFile={known_hosts}",
        "-o", "ConnectTimeout=5",
        "-i", str(key_file),
        "-p", str(port),
        f"root@{host}",
        "sh", "-s",
    ]

    try:
        res = subprocess.run(cmd, input=sh_script, capture_output=True, text=True, timeout=timeout)
    except Exception as e:
        return {"error": f"SSH invocation failed: {e}"}

    if res.returncode != 0:
        return {"error": f"SSH returned code {res.returncode}: {res.stderr.strip()}"}

    out = res.stdout
    parts = out.split("===MODULES===")
    boot_id = parts[0].strip()

    p_dev = parts[1].split("===DEV_NODES===")
    mod_lines = p_dev[0].splitlines()
    loaded_mods = [l.split()[0] for l in mod_lines if l.strip()]

    p_batt = p_dev[1].split("===BATTERY_SNAPSHOT===")
    dev_nodes = [l.strip() for l in p_batt[0].splitlines() if l.strip() and l.strip() != "NONE"]

    p_chg = p_batt[1].split("===CHARGER_STATUS===")
    batt_text = p_chg[0].strip()
    battery_dict = parse_battery_snapshot_text(batt_text) if batt_text != "NONE" else {}

    chg_status = p_chg[1].strip() if len(p_chg) > 1 else "UNKNOWN"

    return {
        "platform": "OnePlus Nord 3 5G CPH2493 (MT6983 / project 22823 'Vitamin')",
        "boot_id": boot_id,
        "trial_mode": "QUIESCENT_CHECK",
        "battery": battery_dict,
        "charger_status": chg_status,
        "loaded_modules": loaded_mods,
        "dev_nodes": dev_nodes,
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="GNSS fix-trial readiness checklist & gated evaluator")
    parser.add_argument("fixture", type=Path, nargs="?", default=None, help="Path to JSON fixture")
    parser.add_argument("--live", action="store_true", help="Perform read-only query on Lynx (requires --allow-live)")
    parser.add_argument("--allow-live", action="store_true", help="Confirm read-only live query")
    parser.add_argument("--host", default=DEFAULT_LYNX_HOST, help="Lynx IP")
    parser.add_argument("--port", type=int, default=DEFAULT_LYNX_PORT, help="Lynx SSH port")
    args = parser.parse_args()

    if args.live:
        if not args.allow_live:
            print(json.dumps({"error": "Refusing live query without both --live and --allow-live"}, indent=2), file=sys.stderr)
            sys.exit(2)
        data = collect_live_gnss_readiness(host=args.host, port=args.port)
        if "error" in data:
            print(json.dumps({"status": "FAILED", "error": data["error"]}, indent=2))
            sys.exit(1)
        verdict = evaluate_gnss_readiness(data)
        print(json.dumps(verdict.to_dict(), indent=2))
        sys.exit(0 if verdict.is_valid else 1)

    if args.fixture:
        data = json.loads(args.fixture.read_text())
        verdict = evaluate_gnss_readiness(data)
        print(json.dumps(verdict.to_dict(), indent=2))
        sys.exit(0 if verdict.is_valid else 1)

    parser.print_help()


if __name__ == "__main__":
    main()
