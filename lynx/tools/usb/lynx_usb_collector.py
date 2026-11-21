#!/usr/bin/env python3
"""Lynx USB ACM Continuity and Acceptance Collector.

Read-only inspection and evaluation tool for the USB ACM serial link between
OnePlus Nord 3 (Lynx) and the Nexus host.

Distinguishes:
1. Phone-side gadget state (MTU3 mode, UDCs, configfs gadget, ttyGS0).
2. Nexus host enumeration (lsusb, udev properties, /dev/ttyACM*).
3. ACM endpoints continuity (both endpoints active vs partial vs missing).
4. Stale observations and boot ID tracking.

Pure evaluator `evaluate_usb_link()` enables deterministic offline testing.
Live collection (`--live`) uses bounded read-only commands without hardware mutation.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

PINNED_V53_BOOT_ID = "0fe847d2-44d6-4ac1-9000-2c99df1a51d8"
EXPECTED_VENDOR_ID = "1d6b"
EXPECTED_PRODUCT_ID = "0104"
DEFAULT_LYNX_HOST = "192.168.100.107"
DEFAULT_LYNX_PORT = 2222
SSH_CONNECT_TIMEOUT = 5
SSH_EXEC_TIMEOUT = 8


def evaluate_usb_link(
    obs: Dict[str, Any], pinned_boot: str = PINNED_V53_BOOT_ID
) -> Dict[str, Any]:
    """Evaluate USB link state purely from an observation dictionary.

    Returns a structured verdict and component breakdowns.
    """
    reasons: List[str] = []

    # Check for timeout or error in observation
    if obs.get("timeout"):
        return {
            "verdict": "timeout",
            "continuity": {
                "both_endpoints_active": False,
                "link_state": "timeout",
            },
            "reasons": [f"Collection timed out: {obs.get('error', 'unspecified')}"]
        }
    if obs.get("collection_error"):
        return {
            "verdict": "error",
            "continuity": {
                "both_endpoints_active": False,
                "link_state": "error",
            },
            "reasons": [f"Collection error: {obs.get('collection_error')}"]
        }

    phone = obs.get("phone", {})
    nexus = obs.get("nexus", {})

    # 1. Phone side checks
    boot_id = phone.get("boot_id", "")
    boot_ok = (boot_id == pinned_boot)
    if not boot_ok and boot_id:
        reasons.append(f"Boot ID mismatch: observed '{boot_id}', expected pinned '{pinned_boot}'")
    elif not boot_id:
        reasons.append("Phone boot ID could not be determined")

    mtu3_mode = phone.get("mtu3_mode")
    udcs = phone.get("udcs", [])
    ttygs_present = bool(phone.get("ttygs_present"))
    gadget_bound = bool(phone.get("gadget_bound"))

    # Phone gadget is considered active if MTU3 is in device mode (mode 3) and ttyGS0 exists
    phone_gadget_active = (mtu3_mode == "3") and ttygs_present and ("11201000.usb0" in udcs)

    if not phone_gadget_active:
        if mtu3_mode != "3":
            reasons.append(f"Phone MTU3 controller is in mode '{mtu3_mode}' (requires '3' for device mode)")
        if not ttygs_present:
            reasons.append("Phone virtual serial node ttyGS0 is not present")
        if "11201000.usb0" not in udcs:
            reasons.append("11201000.usb0 is missing from phone UDCs")

    # 2. Nexus host checks
    ttyacm_present = bool(nexus.get("ttyacm_present"))
    acm_node = nexus.get("device_node")
    vid = nexus.get("vendor_id")
    pid = nexus.get("product_id")
    driver = nexus.get("driver")

    nexus_active = ttyacm_present and (vid == EXPECTED_VENDOR_ID) and (pid == EXPECTED_PRODUCT_ID)

    if not nexus_active:
        if not ttyacm_present:
            reasons.append("Nexus does not see any active /dev/ttyACM* device")
        elif vid != EXPECTED_VENDOR_ID or pid != EXPECTED_PRODUCT_ID:
            reasons.append(f"Nexus enumerated USB device ID mismatch: {vid}:{pid} (expected {EXPECTED_VENDOR_ID}:{EXPECTED_PRODUCT_ID})")

    # 3. Determine Overall Continuity Verdict
    if not boot_ok and boot_id:
        verdict = "stale_boot"
        link_state = "stale_boot"
    elif phone_gadget_active and nexus_active:
        verdict = "connected"
        link_state = "active_bidirectional_candidate"
        reasons.append(f"Full USB ACM link established: Phone /dev/ttyGS0 <-> Nexus {acm_node} (ID {vid}:{pid})")
    elif phone_gadget_active and not nexus_active:
        verdict = "partial"
        link_state = "phone_only"
        reasons.append("Phone gadget is configured in mode 3, but Nexus host has not enumerated ttyACM")
    elif not phone_gadget_active and nexus_active:
        verdict = "partial"
        link_state = "nexus_only"
        reasons.append(f"Nexus sees {acm_node}, but phone reports unconfigured gadget or non-device MTU3 mode")
    else:
        verdict = "disconnected"
        link_state = "disconnected"
        reasons.append("USB link inactive: neither phone gadget nor Nexus ACM endpoint is active")

    return {
        "verdict": verdict,
        "continuity": {
            "both_endpoints_active": (phone_gadget_active and nexus_active and boot_ok),
            "link_state": link_state,
        },
        "phone_gadget": {
            "boot_id": boot_id,
            "boot_id_matches_pinned": boot_ok,
            "mtu3_mode": mtu3_mode,
            "udcs": udcs,
            "ttygs_present": ttygs_present,
            "gadget_bound": gadget_bound,
            "active": phone_gadget_active,
        },
        "nexus_host": {
            "ttyacm_present": ttyacm_present,
            "device_node": acm_node,
            "vendor_id": vid,
            "product_id": pid,
            "serial": nexus.get("serial"),
            "product_name": nexus.get("product_name"),
            "driver": driver,
            "active": nexus_active,
        },
        "reasons": reasons,
    }


def collect_nexus_usb_state() -> Dict[str, Any]:
    """Inspect Nexus host USB subsystem for Lynx gadget."""
    state: Dict[str, Any] = {
        "ttyacm_present": False,
        "device_node": None,
        "vendor_id": None,
        "product_id": None,
        "serial": None,
        "product_name": None,
        "driver": None,
    }

    # Find ttyACM devices
    acm_nodes = sorted(glob.glob("/dev/ttyACM*"))
    for node in acm_nodes:
        # Check udevadm property
        try:
            res = subprocess.run(
                ["udevadm", "info", "-q", "property", node],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            props = {}
            for line in res.stdout.splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    props[k] = v

            vid = props.get("ID_VENDOR_ID")
            pid = props.get("ID_MODEL_ID")
            if vid == EXPECTED_VENDOR_ID and pid == EXPECTED_PRODUCT_ID:
                state["ttyacm_present"] = True
                state["device_node"] = node
                state["vendor_id"] = vid
                state["product_id"] = pid
                state["serial"] = props.get("ID_SERIAL_SHORT") or props.get("ID_SERIAL")
                state["product_name"] = props.get("ID_MODEL")
                state["driver"] = props.get("ID_USB_DRIVER")
                break
        except Exception:
            continue

    return state


def collect_phone_usb_state(
    host: str = DEFAULT_LYNX_HOST, port: int = DEFAULT_LYNX_PORT
) -> Dict[str, Any]:
    """Execute bounded read-only inspection on Lynx over SSH."""
    phone_sh = r"""
cat /proc/sys/kernel/random/boot_id 2>/dev/null || echo "UNKNOWN_BOOT"
echo "===UDC==="
ls -1 /sys/class/udc/ 2>/dev/null
echo "===MODE==="
cat /sys/devices/platform/soc/11201000.usb0/mode 2>/dev/null || echo "UNKNOWN_MODE"
echo "===TTYGS==="
test -e /sys/class/tty/ttyGS0 && echo "EXISTS" || echo "ABSENT"
echo "===CONFIGFS==="
test -d /sys/kernel/config/usb_gadget/g1/configs/c.1 && echo "CONFIGURED" || echo "NOT_CONFIGURED"
"""
    cmd = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "IdentitiesOnly=yes",
        "-o", "StrictHostKeyChecking=yes",
        "-o", "GlobalKnownHostsFile=/dev/null",
        "-o", "HostKeyAlias=lynx",
        "-o", f"UserKnownHostsFile={Path(__file__).resolve().parent.parent.parent}/secrets/lynx_known_hosts",
        "-o", f"ConnectTimeout={SSH_CONNECT_TIMEOUT}",
        "-i", f"{Path(__file__).resolve().parent.parent.parent}/secrets/nexus_lynx_ed25519",
        "-p", str(port),
        f"root@{host}",
        "sh", "-s",
    ]

    try:
        res = subprocess.run(cmd, input=phone_sh, capture_output=True, text=True, timeout=SSH_EXEC_TIMEOUT)
        if res.returncode != 0:
            return {"error": f"SSH returned {res.returncode}: {res.stderr.strip()}"}

        out = res.stdout
        parts = out.split("===UDC===")
        boot_id = parts[0].strip()

        udc_part = parts[1].split("===MODE===") if len(parts) > 1 else ["", ""]
        udcs = [u.strip() for u in udc_part[0].splitlines() if u.strip()]

        mode_part = udc_part[1].split("===TTYGS===") if len(udc_part) > 1 else ["", ""]
        mtu3_mode = mode_part[0].strip()

        tty_part = mode_part[1].split("===CONFIGFS===") if len(mode_part) > 1 else ["", ""]
        ttygs_present = (tty_part[0].strip() == "EXISTS")
        gadget_bound = (tty_part[1].strip() == "CONFIGURED") if len(tty_part) > 1 else False

        return {
            "boot_id": boot_id,
            "udcs": udcs,
            "mtu3_mode": mtu3_mode,
            "ttygs_present": ttygs_present,
            "gadget_bound": gadget_bound,
        }
    except subprocess.TimeoutExpired:
        return {"timeout": True, "error": f"SSH command timed out after {SSH_EXEC_TIMEOUT}s"}
    except Exception as exc:
        return {"collection_error": str(exc)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Lynx USB ACM Continuity and Acceptance Collector")
    parser.add_argument("--live", action="store_true", help="Perform live collection from Nexus and Lynx")
    parser.add_argument("--allow-live", action="store_true", help="Safety gate required to contact Lynx over SSH")
    parser.add_argument("--fixture", type=str, help="Load observation dict from a JSON fixture file")
    parser.add_argument("--pinned-boot", type=str, default=PINNED_V53_BOOT_ID, help="Expected pinned boot ID")
    parser.add_argument("--text", action="store_true", help="Output human-readable text summary instead of JSON")
    args = parser.parse_args()

    if args.fixture:
        with open(args.fixture, "r", encoding="utf-8") as f:
            obs = json.load(f)
    elif args.live:
        if not args.allow_live:
            print("Error: --live requires --allow-live safety flag", file=sys.stderr)
            sys.exit(2)
        phone = collect_phone_usb_state()
        nexus = collect_nexus_usb_state()
        obs = {"phone": phone, "nexus": nexus}
    else:
        # Default: read Nexus state only (offline safe)
        nexus = collect_nexus_usb_state()
        obs = {"phone": {}, "nexus": nexus, "note": "Nexus-only offline snapshot (no live phone probe)"}

    result = evaluate_usb_link(obs, pinned_boot=args.pinned_boot)

    if args.text:
        print(f"USB Link Verdict: {result['verdict'].upper()}")
        print(f"Continuity State: {result['continuity']['link_state']}")
        print(f"Both Endpoints Active: {result['continuity']['both_endpoints_active']}")
        print("Reasons:")
        for r in result["reasons"]:
            print(f"  - {r}")
    else:
        print(json.dumps(result, indent=2))

    if result["verdict"] == "connected":
        sys.exit(0)
    elif result["verdict"] in ("partial", "stale_boot"):
        sys.exit(1)
    else:
        sys.exit(3)


if __name__ == "__main__":
    main()
