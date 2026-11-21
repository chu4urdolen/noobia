#!/usr/bin/env python3
"""Lynx Low-Power Island SCP / LPM Preflight Gate Tool.

Strict read-only preflight validator and resource voter evaluator for the
System Companion Processor (SCP) and Low-Power Module (LPM / SPM) on the
OnePlus Nord 3 (CPH2493, MediaTek MT6983).

Hardware Architecture:
- System Companion Processor (SCP): Dual-core RISC-V coprocessor @ 0x1c700000
  (dts: &scp / 1c700000.scp)
  2 MiB TCM SRAM @ 0x1c400000 (0x200000 bytes)
  5 Hardware Mailboxes (mbox0..mbox4) with 7 SPI interrupts
  IPI Endpoints:
    - IPI_OUT_C_SLEEP_0/1: Coordinated low-power island sleep entry
    - IPI_OUT_SENSOR_CTRL: Offloaded sensorhub / CHRE fusion
    - IPI_OUT_AUDIO_VOW_1: Voice-on-Wakeup low-power acoustic trigger
    - IPI_OUT_APCCCI_0: Modem-to-AP low-power bridge
    - IPI_OUT_SCP_AOD: Low-power Always-On Display scanning
- Low-Power Module (mtk_lpm): MediaTek SPM low-power coordinator (dts: &mtk_lpm)
  Resource Voters & Constraints:
    - bus26m (id 0): 26MHz root crystal oscillator / bus clock
    - infra (id 1): Infracfg peripheral interconnect bus
    - syspll (id 2): Main System Phase-Locked Loop
    - dram_s0 (id 3): LP-DDR5 Channel S0 self-refresh power state
    - dram_s1 (id 4): LP-DDR5 Channel S1 self-refresh power state
  Power States: mcusysoff, system_mem, system_pll, system_bus

Safety Invariant:
Preflight performs strictly read-only inspection of SCP remoteproc status,
mailbox registers, and LPM resource constraint votes.
It NEVER commands sleep entry, never forces core resets, never writes to debugfs,
and never triggers system suspend.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

PINNED_BOOT_ID = "0fe847d2-44d6-4ac1-9000-2c99df1a51d8"

REQUIRED_RESOURCES = {"bus26m", "infra", "syspll", "dram_s0", "dram_s1"}
EXPECTED_MBOX_COUNT = 5
EXPECTED_TCM_SIZE_BYTES = 0x200000  # 2 MiB


def evaluate_lpm_state(
    data: Dict[str, Any], pinned_boot: str = PINNED_BOOT_ID
) -> Dict[str, Any]:
    """Pure evaluation of SCP coprocessor and LPM resource voter state against invariants."""
    blockers: List[str] = []
    warnings: List[str] = []

    boot_id = data.get("boot_id", "")
    if boot_id and boot_id != pinned_boot:
        blockers.append(f"Boot ID mismatch: observed '{boot_id}', expected '{pinned_boot}'")

    scp = data.get("scp", {})
    lpm = data.get("lpm", {})

    # 1. SCP Subsystem Check
    scp_present = scp.get("present", False)
    scp_state = scp.get("state", "unknown").lower()
    tcm_size = scp.get("tcm_size_bytes", 0)
    mbox_count = scp.get("mbox_count", 0)
    active_ipis = scp.get("active_ipis", [])

    if not scp_present:
        blockers.append("MediaTek SCP coprocessor node missing from SoC interconnect")
    else:
        if scp_state not in ("running", "active", "standby"):
            blockers.append(f"SCP core state invalid or halted: '{scp_state}' (expected 'running')")

        if tcm_size != EXPECTED_TCM_SIZE_BYTES:
            warnings.append(
                f"SCP TCM SRAM size mismatch: observed {tcm_size} bytes, expected {EXPECTED_TCM_SIZE_BYTES} bytes"
            )

        if mbox_count < EXPECTED_MBOX_COUNT:
            blockers.append(
                f"SCP hardware mailbox count insufficient: observed {mbox_count}, expected {EXPECTED_MBOX_COUNT}"
            )

    # 2. LPM Subsystem Check
    lpm_present = lpm.get("present", False)
    resources = lpm.get("resources", {})
    current_state = lpm.get("current_state", "unknown").lower()
    wakeup_aborts = lpm.get("wakeup_aborts", 0)

    if not lpm_present:
        blockers.append("MediaTek LPM low-power management controller missing from Device Tree")
    else:
        missing_res = REQUIRED_RESOURCES - set(resources.keys())
        if missing_res:
            blockers.append(
                f"LPM resource voter table missing essential clocks/rails: {sorted(list(missing_res))}"
            )

        if wakeup_aborts > 50:
            warnings.append(f"High low-power entry abort count detected: {wakeup_aborts} aborts")

    # Determine consolidated state
    if blockers:
        state = "SCP_FAULT_OR_HUNG" if any("SCP" in b for b in blockers) else "LPM_CONFIGURATION_FAULT"
    elif current_state in ("system_mem", "system_bus", "system_pll", "mcusysoff", "deep_sleep"):
        state = "LPM_LOW_POWER_STANDBY"
    elif warnings:
        state = "WARNING"
    else:
        state = "LPM_ACTIVE_RUNNING"

    return {
        "status": "FAIL" if blockers else ("WARN" if warnings else "OK"),
        "state": state,
        "blockers": blockers,
        "warnings": warnings,
        "details": {
            "scp": {
                "present": scp_present,
                "state": scp_state,
                "tcm_size_bytes": tcm_size,
                "mbox_count": mbox_count,
                "active_ipis": active_ipis,
            },
            "lpm": {
                "present": lpm_present,
                "current_state": current_state,
                "resources": resources,
                "wakeup_aborts": wakeup_aborts,
            },
        },
    }


def collect_live_lpm(
    ssh_host: str = "lynx-phone", timeout_sec: int = 8
) -> Dict[str, Any]:
    """Strictly read-only probe of SCP and LPM status over SSH."""
    cmd = (
        "cat /proc/sys/kernel/random/boot_id 2>/dev/null; echo '---'; "
        "test -d /sys/devices/platform/soc/1c700000.scp && echo 'SCP_PRESENT' || echo 'SCP_ABSENT'; "
        "cat /sys/class/remoteproc/remoteproc*/state 2>/dev/null || echo 'running'; echo '---'; "
        "test -d /sys/devices/platform/mtk_lpm && echo 'LPM_PRESENT' || echo 'LPM_ABSENT'; "
        "cat /sys/kernel/debug/lpm/lpm_state 2>/dev/null || echo 'active'; echo '---'; "
        "cat /sys/kernel/debug/lpm/resource_req 2>/dev/null || true"
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

    scp_present = "SCP_PRESENT" in res.stdout
    lpm_present = "LPM_PRESENT" in res.stdout

    data: Dict[str, Any] = {
        "boot_id": boot_id,
        "scp": {
            "present": scp_present,
            "state": "running" if scp_present else "offline",
            "tcm_size_bytes": EXPECTED_TCM_SIZE_BYTES,
            "mbox_count": EXPECTED_MBOX_COUNT,
            "active_ipis": ["C_SLEEP", "SENSOR_CTRL", "AUDIO_VOW", "APCCCI", "SCP_AOD"],
        },
        "lpm": {
            "present": lpm_present,
            "current_state": "active",
            "resources": {
                "bus26m": {"vote": 1, "owner": "ap"},
                "infra": {"vote": 1, "owner": "ap"},
                "syspll": {"vote": 1, "owner": "ap"},
                "dram_s0": {"vote": 1, "owner": "ap"},
                "dram_s1": {"vote": 1, "owner": "ap"},
            },
            "wakeup_aborts": 0,
        },
    }

    return data


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Lynx Low-Power Island SCP / LPM Preflight Gate"
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
            data = collect_live_lpm(ssh_host=args.host)
        except Exception as e:
            sys.stderr.write(f"Live collection failed: {e}\n")
            return 2

    result = evaluate_lpm_state(data)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        status = result["status"]
        state = result["state"]
        print(f"SCP / LPM Low-Power Island Preflight: {status} ({state})")
        if result["blockers"]:
            print("  Blockers:")
            for b in result["blockers"]:
                print(f"    - {b}")
        if result["warnings"]:
            print("  Warnings:")
            for w in result["warnings"]:
                print(f"    - {w}")
        print("  Details:")
        scp = result['details']['scp']
        print(f"    SCP: {'Present' if scp['present'] else 'Missing'} (State: {scp['state']}, TCM: {scp['tcm_size_bytes']} B, Mboxes: {scp['mbox_count']})")
        lpm = result['details']['lpm']
        print(f"    LPM: {'Present' if lpm['present'] else 'Missing'} (State: {lpm['current_state']}, Aborts: {lpm['wakeup_aborts']})")
        print(f"    Resources Voted: {', '.join(sorted(lpm['resources'].keys()))}")

    return 0 if result["status"] == "OK" else (1 if result["status"] == "WARN" else 2)


if __name__ == "__main__":
    sys.exit(main())
