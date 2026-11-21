#!/usr/bin/env python3
"""Lynx USB-C DisplayPort Alternate Mode & Redriver Preflight Gate Tool.

Strict read-only preflight validator and configuration evaluator for USB-C
DisplayPort Alternate Mode and high-speed signal conditioning redrivers on
the OnePlus Nord 3 (CPH2493, MediaTek MT6983).

Hardware Architecture:
- Redriver: Parade Technologies PS5170 on I2C6 @ 0x28 (dts: &ps5170 / ps5170@30)
  Controlled via pinctrl &ps_enable / &ps_disable (GPIO204 pins_cmd_dat)
  Kernel module: ps5170.ko (depends on mux_switch, mediatek-drm)
- DP Selector: MediaTek USB DP Selector @ MMIO 0x10005600 (dts: &usb_dp_selector)
  Kernel module: usb_dp_selector.ko (depends on mux_switch, mediatek-drm)
- TCPC / Port Manager: MediaTek MT6375 sub-PMIC TCPC (&mt6375_typec / &typec_mux_switch)
  Standard DisplayPort Alt Mode VDM SVID: 0xff01 (VESA DP Standard)
  Supported Pin Assignments:
    - Pin Assignment C: 4-lane DisplayPort (high-resolution video sink)
    - Pin Assignment D: 2-lane DisplayPort + USB 3.x SuperSpeed multi-function
    - Pin Assignment E: 4-lane DisplayPort alternate pinout
  HPD (Hot Plug Detect) States:
    - 0 / low: Sink disconnected
    - 1 / high: Sink attached & active
    - irq: Attention pulse from sink (HDCP / link renegotiation)

Safety Invariant:
Preflight performs strictly read-only inspection of Device Tree topology, sysfs
Type-C class interfaces, and driver binding state.
It NEVER commands register modifications, never forces DP lane switches, never
toggles power regulators, and never initiates live link training.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

PINNED_BOOT_ID = "0fe847d2-44d6-4ac1-9000-2c99df1a51d8"

# VESA DisplayPort Standard SVID
DP_SVID = 0xFF01
DP_SVID_HEX = "0xff01"

# Recognized Pin Assignments
VALID_PIN_ASSIGNMENTS = {"C", "D", "E"}

EXPECTED_REDRIVER_NODE = "6-0028"
EXPECTED_SELECTOR_NODE = "10005600.usb_dp_selector"
EXPECTED_PORT_NODE = "port0"


def evaluate_usb_dp_state(
    data: Dict[str, Any], pinned_boot: str = PINNED_BOOT_ID
) -> Dict[str, Any]:
    """Pure evaluation of USB-C DisplayPort and redriver state against invariants."""
    blockers: List[str] = []
    warnings: List[str] = []

    boot_id = data.get("boot_id", "")
    if boot_id and boot_id != pinned_boot:
        blockers.append(f"Boot ID mismatch: observed '{boot_id}', expected '{pinned_boot}'")

    redriver = data.get("redriver", {})
    selector = data.get("selector", {})
    tcpc = data.get("tcpc", {})
    modules = data.get("modules", {})

    # 1. Redriver check
    redriver_present = redriver.get("present", False)
    redriver_addr = redriver.get("i2c_address", "")
    pinctrl_state = redriver.get("pinctrl_state", "unknown")

    if not redriver_present:
        blockers.append("Parade PS5170 Type-C redriver node missing from I2C bus")
    elif redriver_addr not in ("0x28", "0x30", 0x28, 0x30):
        warnings.append(f"Unexpected redriver I2C address: {redriver_addr}")

    if pinctrl_state not in ("enable", "disable", "okay", "default"):
        warnings.append(f"Unrecognized redriver pinctrl state: {pinctrl_state}")

    # 2. Selector check
    selector_present = selector.get("present", False)
    selector_mmio = selector.get("mmio_address", "")
    if not selector_present:
        blockers.append("MediaTek USB DP selector node missing from MMIO bus")
    elif selector_mmio and selector_mmio not in ("0x10005600", 0x10005600):
        warnings.append(f"Unexpected selector MMIO address: {selector_mmio}")

    # 3. Module dependencies check
    req_modules = ["ps5170", "usb_dp_selector", "mux_switch"]
    for mod in req_modules:
        if mod in modules and not modules[mod]:
            warnings.append(f"Required kernel module '{mod}' reported inactive or missing")

    # 4. TCPC / Alt Mode check
    port_present = tcpc.get("port_present", False)
    if not port_present:
        blockers.append("Type-C port class interface missing (/sys/class/typec/port0)")

    svid = tcpc.get("svid")
    altmode_active = bool(tcpc.get("altmode_active", False))
    pin_assignment = tcpc.get("pin_assignment")
    hpd_state = str(tcpc.get("hpd", "0")).lower()
    orientation = tcpc.get("orientation", "unknown")

    if altmode_active:
        if svid is not None and svid not in (DP_SVID, DP_SVID_HEX, 65281):
            blockers.append(f"Active Alt Mode SVID mismatch: {svid} (expected {DP_SVID_HEX})")

        if pin_assignment not in VALID_PIN_ASSIGNMENTS:
            blockers.append(
                f"Invalid or unsupported DP pin assignment '{pin_assignment}' (expected C, D, or E)"
            )

        if hpd_state not in ("1", "high", "irq"):
            warnings.append(f"Alt Mode active but HPD indicates inactive or pulsing sink: '{hpd_state}'")

    if orientation not in ("normal", "reversed", "cc1", "cc2", "unknown"):
        warnings.append(f"Unrecognized Type-C cable orientation: '{orientation}'")

    # Determine consolidated state
    if blockers:
        state = "HARDWARE_FAULT"
    elif altmode_active and hpd_state in ("1", "high"):
        state = "DP_ALTMODE_ACTIVE"
    elif altmode_active:
        state = "DP_ALTMODE_NEGOTIATING"
    elif warnings:
        state = "WARNING"
    else:
        state = "DP_STANDBY_DISCONNECTED"

    return {
        "status": "FAIL" if blockers else ("WARN" if warnings else "OK"),
        "state": state,
        "blockers": blockers,
        "warnings": warnings,
        "details": {
            "redriver": {
                "present": redriver_present,
                "address": redriver_addr,
                "pinctrl_state": pinctrl_state,
            },
            "selector": {
                "present": selector_present,
                "mmio": selector_mmio,
            },
            "tcpc": {
                "port_present": port_present,
                "altmode_active": altmode_active,
                "svid": svid,
                "pin_assignment": pin_assignment,
                "hpd": hpd_state,
                "orientation": orientation,
            },
            "modules": modules,
        },
    }


def collect_live_usb_dp(
    ssh_host: str = "lynx-phone", timeout_sec: int = 8
) -> Dict[str, Any]:
    """Strictly read-only probe of USB-C DisplayPort and redriver state over SSH."""
    cmd = (
        "cat /proc/sys/kernel/random/boot_id 2>/dev/null; echo '---'; "
        "test -d /sys/bus/i2c/devices/6-0028 && echo 'REDRIVER_PRESENT' || echo 'REDRIVER_ABSENT'; "
        "test -d /sys/devices/platform/soc/10005600.usb_dp_selector && echo 'SELECTOR_PRESENT' || echo 'SELECTOR_ABSENT'; "
        "test -d /sys/class/typec/port0 && echo 'PORT_PRESENT' || echo 'PORT_ABSENT'; "
        "cat /sys/class/typec/port0/orientation 2>/dev/null; echo '---'; "
        "lsmod 2>/dev/null | grep -E 'ps5170|usb_dp_selector|mux_switch' || true; echo '---'; "
        "find /sys/class/typec/port0*/ -maxdepth 2 -name 'svid' -exec cat {} + 2>/dev/null || true; echo '---'; "
        "find /sys/class/typec/port0*/ -maxdepth 2 -name 'pin_assignment' -exec cat {} + 2>/dev/null || true; echo '---'; "
        "find /sys/class/typec/port0*/ -maxdepth 2 -name 'hpd' -exec cat {} + 2>/dev/null || true"
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

    data: Dict[str, Any] = {
        "boot_id": boot_id,
        "redriver": {
            "present": "REDRIVER_PRESENT" in res.stdout,
            "i2c_address": "0x28",
            "pinctrl_state": "enable",
        },
        "selector": {
            "present": "SELECTOR_PRESENT" in res.stdout,
            "mmio_address": "0x10005600",
        },
        "tcpc": {
            "port_present": "PORT_PRESENT" in res.stdout,
            "altmode_active": False,
            "svid": None,
            "pin_assignment": None,
            "hpd": "0",
            "orientation": "unknown",
        },
        "modules": {
            "ps5170": "ps5170" in res.stdout,
            "usb_dp_selector": "usb_dp_selector" in res.stdout,
            "mux_switch": "mux_switch" in res.stdout,
        },
    }

    if "normal" in res.stdout:
        data["tcpc"]["orientation"] = "normal"
    elif "reversed" in res.stdout:
        data["tcpc"]["orientation"] = "reversed"

    if "ff01" in res.stdout.lower():
        data["tcpc"]["svid"] = DP_SVID_HEX
        data["tcpc"]["altmode_active"] = True

    for p in ("C", "D", "E"):
        if f"[{p}]" in res.stdout or f" {p} " in res.stdout:
            data["tcpc"]["pin_assignment"] = p
            break

    return data


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Lynx USB-C DisplayPort Alt Mode & Redriver Preflight Gate"
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
            data = collect_live_usb_dp(ssh_host=args.host)
        except Exception as e:
            sys.stderr.write(f"Live collection failed: {e}\n")
            return 2

    result = evaluate_usb_dp_state(data)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        status = result["status"]
        state = result["state"]
        print(f"USB-C DisplayPort Alt Mode Preflight: {status} ({state})")
        if result["blockers"]:
            print("  Blockers:")
            for b in result["blockers"]:
                print(f"    - {b}")
        if result["warnings"]:
            print("  Warnings:")
            for w in result["warnings"]:
                print(f"    - {w}")
        print("  Details:")
        print(f"    Redriver: {'Present' if result['details']['redriver']['present'] else 'Missing'} ({result['details']['redriver']['address']})")
        print(f"    Selector: {'Present' if result['details']['selector']['present'] else 'Missing'} ({result['details']['selector']['mmio']})")
        tcpc = result['details']['tcpc']
        print(f"    Alt Mode: {'Active' if tcpc['altmode_active'] else 'Inactive'} (SVID: {tcpc['svid']}, Pin: {tcpc['pin_assignment']}, HPD: {tcpc['hpd']})")

    return 0 if result["status"] == "OK" else (1 if result["status"] == "WARN" else 2)


if __name__ == "__main__":
    sys.exit(main())
