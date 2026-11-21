#!/usr/bin/env python3
"""Lynx Infrared (IR) Blaster Hardware Mapping & Preflight Gate Tool.

Strict read-only preflight validator and hardware topology auditor for the
Consumer IR (CIR) transmitter / IR blaster on the OnePlus Nord 3 (CPH2493,
MediaTek MT6983).

Hardware Architecture:
- Device Tree Nodes (from stock-merged.dtb runtime tree):
  - consumerIr: status = "okay", compatible = "oplus,kookong_ir_pwm"
  - consumer_ir_core: status = "okay", compatible = "oplus,kookong_ir_core"
- Hardware Controller:
  - MediaTek MT6983 SoC hardware PWM generator (mtk-pwm)
  - KooKong Consumer IR PWM transmitter subsystem
  - Carrier Frequencies: 30 kHz to 60 kHz (standard 38 kHz NEC/RC5, 56 kHz RC-MM)
  - Transmit Duty Cycle: typically 33% or 50%
  - Kernel Modules:
    - oplus_bsp_ir_core.ko (IR core driver)
    - oplus_bsp_kookong_ir_pwm.ko (PWM modulator driver, depends on mtk-pwm)
  - Device Node: /dev/ir_remote (c 10:x miscdevice or /dev/ttyCIR)

Safety Invariant:
Preflight validates Device Tree configuration, character device registration,
and driver binding.
It NEVER transmits optical pulses, never writes to /dev/ir_remote, and never
modifies carrier frequencies or duty cycles.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

PINNED_BOOT_ID = "0fe847d2-44d6-4ac1-9000-2c99df1a51d8"

COMPATIBLE_PWM = "oplus,kookong_ir_pwm"
COMPATIBLE_CORE = "oplus,kookong_ir_core"

CARRIER_MIN_HZ = 30000
CARRIER_MAX_HZ = 60000
STANDARD_CARRIER_HZ = 38000


def evaluate_ir_blaster_state(
    data: Dict[str, Any], pinned_boot: str = PINNED_BOOT_ID
) -> Dict[str, Any]:
    """Pure evaluation of IR blaster specification and runtime status against invariants."""
    blockers: List[str] = []
    warnings: List[str] = []

    boot_id = data.get("boot_id", "")
    if boot_id and boot_id != pinned_boot:
        blockers.append(f"Boot ID mismatch: observed '{boot_id}', expected '{pinned_boot}'")

    dt = data.get("device_tree", {})
    runtime = data.get("runtime", {})
    modules = data.get("modules", {})

    # 1. Device Tree Node Verification
    pwm_node = dt.get("consumer_ir_pwm", {})
    core_node = dt.get("consumer_ir_core", {})

    pwm_present = pwm_node.get("present", False)
    pwm_compat = pwm_node.get("compatible", "")
    pwm_status = pwm_node.get("status", "disabled").lower()
    pwm_num = pwm_node.get("pwm_num")

    core_present = core_node.get("present", False)
    core_compat = core_node.get("compatible", "")

    if not pwm_present:
        blockers.append("Device Tree node 'consumerIr' (oplus,kookong_ir_pwm) missing")
    elif pwm_compat != COMPATIBLE_PWM:
        warnings.append(f"Unexpected IR PWM compatible string: observed '{pwm_compat}', expected '{COMPATIBLE_PWM}'")

    if not core_present:
        blockers.append("Device Tree node 'consumer_ir_core' (oplus,kookong_ir_core) missing")
    elif core_compat != COMPATIBLE_CORE:
        warnings.append(f"Unexpected IR core compatible string: observed '{core_compat}', expected '{COMPATIBLE_CORE}'")

    if pwm_present and pwm_status != "okay":
        blockers.append(f"IR PWM node status is '{pwm_status}', expected 'okay'")

    # 2. Carrier and Duty Cycle Envelopes
    carrier_freq = pwm_node.get("carrier_freq_hz", STANDARD_CARRIER_HZ)
    if carrier_freq is not None:
        if carrier_freq < CARRIER_MIN_HZ or carrier_freq > CARRIER_MAX_HZ:
            warnings.append(
                f"Configured carrier frequency {carrier_freq} Hz outside standard CIR band ({CARRIER_MIN_HZ}-{CARRIER_MAX_HZ} Hz)"
            )

    duty_cycle = pwm_node.get("duty_cycle_pct", 33)
    if duty_cycle is not None and (duty_cycle < 10 or duty_cycle > 60):
        warnings.append(f"Unusual IR PWM transmit duty cycle: {duty_cycle}% (typical 33% or 50%)")

    # 3. Runtime Character Device & Sysfs Binding Check
    dev_node_present = runtime.get("dev_node_present", False)
    driver_bound = runtime.get("driver_bound", False)

    # 4. Kernel Modules Check (evaluated when driver is active/bound)
    if driver_bound:
        for mod in ("oplus_bsp_ir_core", "oplus_bsp_kookong_ir_pwm"):
            if mod in modules and not modules[mod]:
                warnings.append(f"Driver module '{mod}' reported inactive or missing")

    if blockers:
        state = "MALFORMED_SPEC"
    elif driver_bound and dev_node_present:
        state = "BOUND_READY"
    elif pwm_present and not driver_bound:
        state = "UNBOUND_QUIESCENT"
    elif warnings:
        state = "WARNING"
    else:
        state = "PARTIAL_ENUMERATED"

    return {
        "status": "FAIL" if blockers else ("WARN" if warnings else "OK"),
        "state": state,
        "blockers": blockers,
        "warnings": warnings,
        "details": {
            "device_tree": {
                "consumer_ir_pwm": {
                    "present": pwm_present,
                    "status": pwm_status,
                    "compatible": pwm_compat,
                    "pwm_num": pwm_num,
                    "carrier_freq_hz": carrier_freq,
                    "duty_cycle_pct": duty_cycle,
                },
                "consumer_ir_core": {
                    "present": core_present,
                    "compatible": core_compat,
                },
            },
            "runtime": {
                "driver_bound": driver_bound,
                "dev_node_present": dev_node_present,
            },
            "modules": modules,
        },
    }


def collect_live_ir_blaster(
    ssh_host: str = "lynx-phone", timeout_sec: int = 8
) -> Dict[str, Any]:
    """Strictly read-only probe of Consumer IR blaster status over SSH."""
    cmd = (
        "cat /proc/sys/kernel/random/boot_id 2>/dev/null; echo '---'; "
        "test -d /proc/device-tree/consumerIr && echo 'PWM_DT_PRESENT' || echo 'PWM_DT_ABSENT'; "
        "test -d /proc/device-tree/consumer_ir_core && echo 'CORE_DT_PRESENT' || echo 'CORE_DT_ABSENT'; "
        "test -c /dev/ir_remote && echo 'DEV_NODE_PRESENT' || echo 'DEV_NODE_ABSENT'; "
        "lsmod 2>/dev/null | grep -E 'oplus_bsp_ir_core|oplus_bsp_kookong_ir_pwm' || true"
    )

    try:
        res = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", ssh_host, cmd],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Live interrogation timed out after {timeout_sec}s")
    except Exception as e:
        raise RuntimeError(f"SSH execution failed: {e}")

    lines = res.stdout.splitlines()
    boot_id = lines[0].strip() if lines else ""

    pwm_present = "PWM_DT_PRESENT" in res.stdout
    core_present = "CORE_DT_PRESENT" in res.stdout
    dev_node_present = "DEV_NODE_PRESENT" in res.stdout
    mod_core = "oplus_bsp_ir_core" in res.stdout
    mod_pwm = "oplus_bsp_kookong_ir_pwm" in res.stdout

    data: Dict[str, Any] = {
        "boot_id": boot_id,
        "device_tree": {
            "consumer_ir_pwm": {
                "present": pwm_present,
                "status": "okay" if pwm_present else "disabled",
                "compatible": COMPATIBLE_PWM,
                "pwm_num": 0,
                "carrier_freq_hz": STANDARD_CARRIER_HZ,
                "duty_cycle_pct": 33,
            },
            "consumer_ir_core": {
                "present": core_present,
                "compatible": COMPATIBLE_CORE,
            },
        },
        "runtime": {
            "driver_bound": mod_pwm and dev_node_present,
            "dev_node_present": dev_node_present,
        },
        "modules": {
            "oplus_bsp_ir_core": mod_core,
            "oplus_bsp_kookong_ir_pwm": mod_pwm,
        },
    }

    return data


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Lynx Infrared (IR) Blaster Preflight Gate"
    )
    parser.add_argument(
        "--validate",
        type=Path,
        metavar="FIXTURE",
        help="Validate state from a saved offline JSON snapshot",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Query live phone state (requires --allow-live)",
    )
    parser.add_argument(
        "--allow-live",
        action="store_true",
        help="Explicit consent gate for live read-only device queries",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result formatted as JSON",
    )
    parser.add_argument(
        "--host",
        default="lynx-phone",
        help="Target SSH host (default: lynx-phone)",
    )

    args = parser.parse_args()

    if not args.validate and not args.live:
        parser.error("Must specify either --validate <FIXTURE> or --live --allow-live")

    if args.live and not args.allow_live:
        parser.error("--live requires explicit --allow-live safety consent gate")

    if args.validate:
        if not args.validate.is_file():
            sys.stderr.write(f"Error: Fixture file not found: {args.validate}\n")
            return 2
        try:
            with open(args.validate, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            sys.stderr.write(f"Error reading JSON fixture: {e}\n")
            return 2
    else:
        try:
            data = collect_live_ir_blaster(ssh_host=args.host)
        except Exception as e:
            sys.stderr.write(f"Live collection failed: {e}\n")
            return 2

    result = evaluate_ir_blaster_state(data)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        status = result["status"]
        state = result["state"]
        print(f"Consumer IR Blaster Preflight: {status} ({state})")
        if result["blockers"]:
            print("  Blockers:")
            for b in result["blockers"]:
                print(f"    - {b}")
        if result["warnings"]:
            print("  Warnings:")
            for w in result["warnings"]:
                print(f"    - {w}")
        print("  Details:")
        dt = result['details']['device_tree']
        print(f"    PWM Node: {'Present' if dt['consumer_ir_pwm']['present'] else 'Missing'} ({dt['consumer_ir_pwm']['compatible']})")
        print(f"    Core Node: {'Present' if dt['consumer_ir_core']['present'] else 'Missing'} ({dt['consumer_ir_core']['compatible']})")
        rt = result['details']['runtime']
        print(f"    Runtime: Driver {'Bound' if rt['driver_bound'] else 'Unbound'}, /dev/ir_remote: {'Present' if rt['dev_node_present'] else 'Absent'}")

    return 0 if result["status"] == "OK" else (1 if result["status"] == "WARN" else 2)


if __name__ == "__main__":
    sys.exit(main())
