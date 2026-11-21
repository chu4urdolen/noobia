#!/usr/bin/env python3
"""Lynx Fingerprint Hardware and Secure Boundary Inventory Tool.

Read-only inspection and evaluation tool for the OnePlus Nord 3 (Lynx)
optical under-display fingerprint sensor subsystem.

Separates and distinguishes:
1. Hardware Bus & DT Presence (SPI bus 7, CS 0, DT node oplus,fp_spi).
2. Linux Kernel Driver Layer (uff_fp_driver, oplus_fp_common, spi-mt65xx).
3. Trust Execution Environment (TEE) Layer (mcDrvModule, /dev/mobicore, mcDriverDaemon).
4. Userspace Android HAL Layer (vendor.oplus.hardware.biometrics.fingerprint).

Deterministic evaluation via pure function `evaluate_fingerprint_inventory()`.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, List, Optional

PINNED_V53_BOOT_ID = "0fe847d2-44d6-4ac1-9000-2c99df1a51d8"
EXPECTED_DT_COMPATIBLE = "oplus,fp_spi"
DEFAULT_LYNX_HOST = "192.168.100.107"
DEFAULT_LYNX_PORT = 2222
SSH_TIMEOUT = 8


def evaluate_fingerprint_inventory(
    obs: Dict[str, Any], pinned_boot: str = PINNED_V53_BOOT_ID
) -> Dict[str, Any]:
    """Evaluate fingerprint subsystem inventory from observation dictionary."""
    if obs.get("timeout"):
        return {
            "verdict": "timeout",
            "error": obs.get("error", "Command timed out"),
            "gaps": ["Telemetry collection timed out"],
        }
    if obs.get("error"):
        return {
            "verdict": "error",
            "error": obs.get("error"),
            "gaps": [f"Telemetry collection error: {obs.get('error')}"],
        }

    phone = obs.get("phone", {})
    boot_id = phone.get("boot_id", "")
    boot_ok = (boot_id == pinned_boot)

    dt = phone.get("device_tree", {})
    spi = phone.get("spi_bus", {})
    modules = phone.get("modules", [])
    devices = phone.get("devices", {})
    daemons = phone.get("daemons", [])

    gaps: List[str] = []

    # 1. Hardware & DT Layer
    dt_present = bool(dt.get("present"))
    dt_compatible = dt.get("compatible", "")
    spi_dev_present = bool(spi.get("present"))

    hw_present = dt_present and (EXPECTED_DT_COMPATIBLE in dt_compatible) and spi_dev_present
    if not dt_present:
        gaps.append("Device tree node for fingerprint@0 is missing")
    elif EXPECTED_DT_COMPATIBLE not in dt_compatible:
        gaps.append(f"DT compatible mismatch: got '{dt_compatible}', expected '{EXPECTED_DT_COMPATIBLE}'")
    if not spi_dev_present:
        gaps.append("SPI bus device spi7.0 is not enumerated in /sys/bus/spi/devices/")

    # 2. Kernel Driver Layer
    driver_bound = bool(spi.get("driver_bound"))
    driver_name = spi.get("driver_name")
    uff_loaded = ("uff_fp_driver" in modules)
    fp_common_loaded = ("oplus_fp_common" in modules)
    spi_master_loaded = ("spi_mt65xx" in modules)

    if driver_bound:
        driver_state = "driver_bound"
    elif uff_loaded:
        driver_state = "driver_loaded_unbound"
        gaps.append("Driver uff_fp_driver is loaded in kernel memory but failed to bind to spi7.0")
    else:
        driver_state = "missing_driver"
        gaps.append("Kernel driver uff_fp_driver is not loaded (stock vendor module needed)")

    if not spi_master_loaded:
        gaps.append("MediaTek SPI master controller driver spi_mt65xx is not resident")

    # 3. TEE Boundary Layer
    mobicore_driver_loaded = ("mcDrvModule" in modules)
    mobicore_dev_present = bool(devices.get("mobicore_dev"))
    mobicore_daemon_running = any("mcDriverDaemon" in d for d in daemons)

    if mobicore_driver_loaded and mobicore_dev_present and mobicore_daemon_running:
        tee_state = "tee_ready"
    elif mobicore_driver_loaded:
        tee_state = "tee_driver_loaded"
        gaps.append("Trustonic TEE kernel module mcDrvModule is loaded, but mcDriverDaemon is not running")
    else:
        tee_state = "tee_driver_missing"
        gaps.append("Trustonic TEE kernel driver mcDrvModule is not loaded")

    # 4. Userspace Android HAL Layer
    fp_char_dev = bool(devices.get("fingerprint_dev"))
    hal_running = any("fingerprint" in d for d in daemons)

    if hal_running:
        userspace_state = "hal_running"
    elif fp_char_dev:
        userspace_state = "char_dev_present_hal_absent"
        gaps.append("/dev/fingerprint_dev exists, but stock Android biometrics HAL daemon is not running")
    else:
        userspace_state = "hal_absent"
        gaps.append("Stock biometrics HAL daemon and /dev/fingerprint_dev are absent (Alpine userspace)")

    # 5. Overall Verdict Classification
    if not boot_ok and boot_id:
        verdict = "stale_boot"
    elif not hw_present:
        verdict = "hardware_missing"
    elif driver_bound and (tee_state == "tee_ready") and hal_running:
        verdict = "biometrics_stack_complete"
    elif driver_bound:
        verdict = "hardware_present_driver_bound"
    else:
        verdict = "hardware_present_driver_missing"

    return {
        "verdict": verdict,
        "boot_id": boot_id,
        "boot_id_matches_pinned": boot_ok,
        "layers": {
            "hardware": {
                "present": hw_present,
                "dt_node": dt.get("path"),
                "dt_compatible": dt_compatible,
                "spi_bus_device": spi.get("device_node"),
                "spi_master_driver": "spi_mt65xx" if spi_master_loaded else "unloaded",
            },
            "kernel_driver": {
                "state": driver_state,
                "driver_bound": driver_bound,
                "driver_name": driver_name,
                "uff_driver_loaded": uff_loaded,
                "fp_common_loaded": fp_common_loaded,
            },
            "tee_boundary": {
                "state": tee_state,
                "mobicore_driver_loaded": mobicore_driver_loaded,
                "mobicore_device_node": mobicore_dev_present,
                "daemon_running": mobicore_daemon_running,
            },
            "userspace": {
                "state": userspace_state,
                "character_device": fp_char_dev,
                "hal_service_running": hal_running,
            },
        },
        "gaps": gaps,
    }


def collect_phone_fingerprint_inventory(
    host: str = DEFAULT_LYNX_HOST, port: int = DEFAULT_LYNX_PORT
) -> Dict[str, Any]:
    """Execute bounded read-only inspection of fingerprint subsystem on Lynx."""
    sh_script = r"""
cat /proc/sys/kernel/random/boot_id 2>/dev/null || echo "UNKNOWN_BOOT"
echo "===DT==="
cat /sys/firmware/devicetree/base/spi7@11017000/fingerprint@0/compatible 2>/dev/null || echo "ABSENT"
echo "===SPI==="
test -d /sys/bus/spi/devices/spi7.0 && echo "EXISTS" || echo "ABSENT"
test -L /sys/bus/spi/devices/spi7.0/driver && echo "BOUND" || echo "UNBOUND"
readlink -f /sys/bus/spi/devices/spi7.0/driver 2>/dev/null || echo "NONE"
echo "===MODULES==="
lsmod
echo "===DEVICES==="
test -e /dev/fingerprint_dev && echo "FP_DEV_EXISTS" || echo "FP_DEV_ABSENT"
test -e /dev/mobicore && echo "MC_DEV_EXISTS" || echo "MC_DEV_ABSENT"
echo "===PS==="
ps -ef 2>/dev/null || ps
"""
    cmd = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "IdentitiesOnly=yes",
        "-o", "StrictHostKeyChecking=yes",
        "-o", "GlobalKnownHostsFile=/dev/null",
        "-o", "HostKeyAlias=lynx",
        "-o", f"UserKnownHostsFile={Path(__file__).resolve().parent.parent.parent}/secrets/lynx_known_hosts",
        "-o", "ConnectTimeout=5",
        "-i", f"{Path(__file__).resolve().parent.parent.parent}/secrets/nexus_lynx_ed25519",
        "-p", str(port),
        f"root@{host}",
        "sh", "-s",
    ]

    try:
        res = subprocess.run(cmd, input=sh_script, capture_output=True, text=True, timeout=SSH_TIMEOUT)
        if res.returncode != 0:
            return {"error": f"SSH returned {res.returncode}: {res.stderr.strip()}"}

        out = res.stdout
        parts = out.split("===DT===")
        boot_id = parts[0].strip()

        dt_part = parts[1].split("===SPI===") if len(parts) > 1 else ["", ""]
        dt_compat = dt_part[0].strip()

        spi_part = dt_part[1].split("===MODULES===") if len(dt_part) > 1 else ["", ""]
        spi_lines = spi_part[0].strip().splitlines()
        spi_exists = (spi_lines[0].strip() == "EXISTS") if len(spi_lines) > 0 else False
        spi_bound = (spi_lines[1].strip() == "BOUND") if len(spi_lines) > 1 else False
        driver_path = spi_lines[2].strip() if len(spi_lines) > 2 else "NONE"
        driver_name = Path(driver_path).name if (spi_bound and driver_path != "NONE") else None

        mod_part = spi_part[1].split("===DEVICES===") if len(spi_part) > 1 else ["", ""]
        modules = [line.split()[0] for line in mod_part[0].strip().splitlines() if line.split()]

        dev_part = mod_part[1].split("===PS===") if len(mod_part) > 1 else ["", ""]
        dev_lines = dev_part[0].strip().splitlines()
        fp_dev = any("FP_DEV_EXISTS" in l for l in dev_lines)
        mc_dev = any("MC_DEV_EXISTS" in l for l in dev_lines)

        ps_lines = dev_part[1].strip().splitlines() if len(dev_part) > 1 else []

        return {
            "phone": {
                "boot_id": boot_id,
                "device_tree": {
                    "present": (dt_compat != "ABSENT"),
                    "compatible": dt_compat,
                    "path": "/sys/firmware/devicetree/base/spi7@11017000/fingerprint@0",
                },
                "spi_bus": {
                    "present": spi_exists,
                    "device_node": "/sys/bus/spi/devices/spi7.0",
                    "driver_bound": spi_bound,
                    "driver_name": driver_name,
                },
                "modules": modules,
                "devices": {
                    "fingerprint_dev": fp_dev,
                    "mobicore_dev": mc_dev,
                },
                "daemons": ps_lines,
            }
        }
    except subprocess.TimeoutExpired:
        return {"timeout": True, "error": f"SSH timed out after {SSH_TIMEOUT}s"}
    except Exception as exc:
        return {"error": str(exc)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Lynx Fingerprint Hardware and Secure Boundary Inventory")
    parser.add_argument("--live", action="store_true", help="Perform read-only live inspection over SSH")
    parser.add_argument("--allow-live", action="store_true", help="Safety gate required to contact Lynx")
    parser.add_argument("--fixture", type=str, help="Load observation from JSON fixture file")
    parser.add_argument("--pinned-boot", type=str, default=PINNED_V53_BOOT_ID, help="Expected pinned boot ID")
    parser.add_argument("--text", action="store_true", help="Output human-readable text summary")
    args = parser.parse_args()

    if args.fixture:
        with open(args.fixture, "r", encoding="utf-8") as f:
            obs = json.load(f)
    elif args.live:
        if not args.allow_live:
            print("Error: --live requires --allow-live safety flag", file=sys.stderr)
            sys.exit(2)
        obs = collect_phone_fingerprint_inventory()
    else:
        print("Error: Specify --live --allow-live or --fixture <path>", file=sys.stderr)
        sys.exit(2)

    result = evaluate_fingerprint_inventory(obs, pinned_boot=args.pinned_boot)

    if args.text:
        print(f"Fingerprint Subsystem Verdict: {result['verdict'].upper()}")
        print(f"Boot ID: {result.get('boot_id')} (matches pinned: {result.get('boot_id_matches_pinned')})")
        print("\nLayer Breakdown:")
        hw = result["layers"]["hardware"]
        drv = result["layers"]["kernel_driver"]
        tee = result["layers"]["tee_boundary"]
        usr = result["layers"]["userspace"]
        print(f"  Hardware:      {'PRESENT' if hw['present'] else 'MISSING'} (DT: {hw['dt_compatible']}, Bus: {hw['spi_bus_device']})")
        print(f"  Kernel Driver: {drv['state'].upper()} (bound: {drv['driver_bound']}, uff: {drv['uff_driver_loaded']})")
        print(f"  TEE Boundary:  {tee['state'].upper()} (mcDrv: {tee['mobicore_driver_loaded']}, dev: {tee['mobicore_device_node']})")
        print(f"  Userspace HAL: {usr['state'].upper()} (char_dev: {usr['character_device']}, daemon: {usr['hal_service_running']})")
        if result["gaps"]:
            print("\nIdentified Gaps:")
            for g in result["gaps"]:
                print(f"  - {g}")
    else:
        print(json.dumps(result, indent=2))

    if result["verdict"] in ("biometrics_stack_complete", "hardware_present_driver_bound"):
        sys.exit(0)
    elif result["verdict"] == "hardware_present_driver_missing":
        sys.exit(1)
    else:
        sys.exit(3)


if __name__ == "__main__":
    main()
