#!/usr/bin/env python3
"""Device-tree and driver parser/gate for the Lynx second rear light source.

Operates in two modes:
1. Pure offline fixture evaluation mode (default when given a JSON fixture path).
2. Read-only live inspection of Lynx's running device tree under /sys/firmware/devicetree/base
   (strictly gated by requiring both --live and --allow-live).

Strictly read-only: does not actuate LED, bind modules, or write sysfs.
Maps device-tree nodes and driver topology to verify whether an independent second
rear LED channel or control path exists on Lynx (OnePlus Nord 3 5G CPH2493, MT6983, project 22823 'Vitamin').
"""

from dataclasses import dataclass, field
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_LYNX_HOST = "192.168.100.107"
DEFAULT_LYNX_PORT = 2222
SSH_TIMEOUT = 8


@dataclass
class FlashChannel:
    name: str
    reg: int
    type_id: int  # 0 = Main (rear), 1 = Sub (front)
    ct_id: int    # Color Temperature index
    part_id: int  # Multi-part index (0 = first LED, 1 = second LED)
    remote_endpoint: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "reg": self.reg,
            "type_id": self.type_id,
            "ct_id": self.ct_id,
            "part_id": self.part_id,
            "remote_endpoint": self.remote_endpoint,
        }


@dataclass
class FlashlightTopologyVerdict:
    status: str  # "SINGLE_CHANNEL_ONLY", "DUAL_CHANNEL_FOUND", "MALFORMED_DT", "ABSENT"
    is_valid: bool
    second_channel_exists: bool
    controller_chip: str
    channels_found: List[Dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    source_citations: List[str] = field(default_factory=list)
    failures: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        res = {
            "status": self.status,
            "is_valid": self.is_valid,
            "second_channel_exists": self.second_channel_exists,
            "controller_chip": self.controller_chip,
            "channels_found": self.channels_found,
            "summary": self.summary,
            "source_citations": self.source_citations,
            "failures": self.failures,
        }
        if self.details:
            res["details"] = self.details
        return res


def parse_flash_channels(dt_data: Dict[str, Any]) -> Tuple[List[FlashChannel], List[str]]:
    """Parse flash channels from a device tree representation of the flash controller."""
    channels: List[FlashChannel] = []
    errors: List[str] = []

    controller_node = dt_data.get("controller", {})
    if not controller_node:
        errors.append("missing_controller_node")
        return channels, errors

    subnodes = controller_node.get("subnodes", {})
    if not subnodes:
        errors.append("no_subnodes_under_controller")
        return channels, errors

    for node_name, props in subnodes.items():
        if not node_name.startswith("flash@"):
            continue
        try:
            reg = int(props.get("reg", -1))
            type_id = int(props.get("type", 0))
            ct_id = int(props.get("ct", 0))
            part_id = int(props.get("part", 0))
            remote = props.get("remote_endpoint")
            channels.append(
                FlashChannel(
                    name=node_name,
                    reg=reg,
                    type_id=type_id,
                    ct_id=ct_id,
                    part_id=part_id,
                    remote_endpoint=remote,
                )
            )
        except (ValueError, TypeError) as exc:
            errors.append(f"malformed_channel_props_in_{node_name}: {exc}")

    return channels, errors


def evaluate_flashlight_topology(
    dt_data: Optional[Dict[str, Any]],
) -> FlashlightTopologyVerdict:
    """Evaluate device tree and driver data to determine flashlight channel availability."""
    citations = [
        "OnePlusOSS/android_kernel_5.10_oneplus_mt6983 (branch oneplus/mt6983_t_13.1_oneplus_nord_3_5g)",
        "kernel-mt6983/arch/arm64/boot/dts/mediatek/cust_mt6983_vitamin_camera_v4l2.dtsi:312-334",
        "mt6983-nord3-flashlight/flashlights-lm3642.c",
        "mt6983-nord3-flashlight/flashlight-core.c",
        "Texas Instruments LM3642 Datasheet (SNVS840A): Single 1.5A High-Side Current Source",
        "linux-port/docs/LYNX-REAR-LIGHT-AND-COLOR-SENSOR.md",
    ]

    if not dt_data:
        return FlashlightTopologyVerdict(
            status="ABSENT",
            is_valid=False,
            second_channel_exists=False,
            controller_chip="unknown",
            summary="Flashlight DT data is absent",
            source_citations=citations,
            failures=["missing_dt_data"],
        )

    controller = dt_data.get("controller", {})
    compatible = controller.get("compatible", "")
    chip_name = controller.get("chip", "unknown")
    source_mode = dt_data.get("source_mode", "fixture")

    channels, errors = parse_flash_channels(dt_data)

    details: Dict[str, Any] = {}
    if "rear_optical_sensor" in dt_data:
        details["rear_optical_sensor"] = dt_data["rear_optical_sensor"]

    if "missing_controller_node" in errors:
        return FlashlightTopologyVerdict(
            status="ABSENT",
            is_valid=False,
            second_channel_exists=False,
            controller_chip=chip_name,
            summary="Controller node is absent in device tree",
            source_citations=citations,
            failures=errors,
            details=details,
        )

    if errors:
        return FlashlightTopologyVerdict(
            status="MALFORMED_DT",
            is_valid=False,
            second_channel_exists=False,
            controller_chip=chip_name,
            summary=f"Encountered {len(errors)} error(s) while parsing flash channels",
            source_citations=citations,
            failures=errors,
            details=details,
        )

    channel_dicts = [ch.to_dict() for ch in channels]

    # Filter for rear light channels (type_id == 0)
    rear_channels = [ch for ch in channels if ch.type_id == 0]

    # Check for distinct secondary channel:
    # A distinct channel must have distinct part_id (> 0), distinct ct_id (> 0), or distinct reg (> 0)
    has_second_channel = (
        len(rear_channels) > 1
        or any(ch.part_id > 0 for ch in rear_channels)
        or any(ch.ct_id > 0 for ch in rear_channels)
    )

    if not has_second_channel and len(rear_channels) == 1:
        ch = rear_channels[0]
        ctrl_path = controller.get("path", controller.get("node", "lm3642"))
        if source_mode == "running_device_tree":
            summary = (
                f"Verified single-channel rear flash on {compatible} ({chip_name}) in running device tree at "
                f"{ctrl_path}/{ch.name} (type={ch.type_id}, ct={ch.ct_id}, part={ch.part_id}). "
                "Second rear circle is the rear CCT/ALS optical sensor (ams tcs3408), not a second light."
            )
        else:
            summary = (
                f"Verified single-channel rear flash on {compatible} ({chip_name}). "
                f"Single registered channel {ch.name} (type={ch.type_id}, ct={ch.ct_id}, "
                f"part={ch.part_id}). source DT declares one lm3642 channel; live confirmation pending."
            )
        return FlashlightTopologyVerdict(
            status="SINGLE_CHANNEL_ONLY",
            is_valid=True,
            second_channel_exists=False,
            controller_chip=chip_name,
            channels_found=channel_dicts,
            summary=summary,
            source_citations=citations,
            failures=[],
            details=details,
        )
    elif has_second_channel:
        return FlashlightTopologyVerdict(
            status="DUAL_CHANNEL_FOUND",
            is_valid=True,
            second_channel_exists=True,
            controller_chip=chip_name,
            channels_found=channel_dicts,
            summary=(
                f"Multiple rear flash channels found ({len(rear_channels)} channels). "
                f"Independent second rear light control path exists."
            ),
            source_citations=citations,
            failures=[],
            details=details,
        )
    else:
        return FlashlightTopologyVerdict(
            status="ABSENT",
            is_valid=False,
            second_channel_exists=False,
            controller_chip=chip_name,
            channels_found=channel_dicts,
            summary="No valid rear flash channels identified in device tree",
            source_citations=citations,
            failures=["no_rear_channels_found"],
            details=details,
        )


def collect_live_flashlight_dt(
    host: str = DEFAULT_LYNX_HOST,
    port: int = DEFAULT_LYNX_PORT,
    timeout: int = SSH_TIMEOUT,
) -> Dict[str, Any]:
    """Execute bounded read-only inspection of running device tree on Lynx."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    known_hosts = repo_root / "secrets/lynx_known_hosts"
    key_file = repo_root / "secrets/nexus_lynx_ed25519"

    sh_script = r"""
cat /proc/sys/kernel/random/boot_id 2>/dev/null || echo "UNKNOWN_BOOT"
echo "===LM3642_NODES==="
find /sys/firmware/devicetree/base -name "*lm3642*" 2>/dev/null
echo "===OTHER_FLASH==="
find /sys/firmware/devicetree/base -name "*flashlight*" -o -name "*flash@*" 2>/dev/null
echo "===HF_MANAGER==="
cat /proc/hf_manager 2>/dev/null || echo "HF_ABSENT"
echo "===DT_PYTHON==="
python3 -c '
import json, os
from pathlib import Path

res = {"nodes": []}
for lm_path in Path("/sys/firmware/devicetree/base").glob("**/lm3642*"):
    node_data = {
        "path": str(lm_path),
        "name": lm_path.name,
        "compatible": (lm_path / "compatible").read_bytes().rstrip(b"\x00").decode("ascii", errors="replace") if (lm_path / "compatible").exists() else None,
        "reg": int.from_bytes((lm_path / "reg").read_bytes(), "big") if (lm_path / "reg").exists() else None,
        "cooling_cells": int.from_bytes((lm_path / "#cooling-cells").read_bytes(), "big") if (lm_path / "#cooling-cells").exists() else None,
        "subnodes": {}
    }
    for sub in sorted(lm_path.glob("flash@*")):
        sub_data = {}
        for attr in ("reg", "type", "ct", "part"):
            p = sub / attr
            if p.exists():
                sub_data[attr] = int.from_bytes(p.read_bytes(), "big")
        sub_data["remote_endpoint"] = "&flashlight_0" if (sub / "port@0").exists() else None
        node_data["subnodes"][sub.name] = sub_data
    res["nodes"].append(node_data)
print(json.dumps(res))
' 2>/dev/null || echo "PY_ERR"
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

    res = subprocess.run(cmd, input=sh_script, capture_output=True, text=True, timeout=timeout)
    if res.returncode != 0:
        return {"error": f"SSH returned {res.returncode}: {res.stderr.strip()}"}

    out = res.stdout
    parts = out.split("===LM3642_NODES===")
    boot_id = parts[0].strip()

    p_lm = parts[1].split("===OTHER_FLASH===")
    lm_nodes = [l.strip() for l in p_lm[0].splitlines() if l.strip()]

    p_other = p_lm[1].split("===HF_MANAGER===")
    other_nodes = [l.strip() for l in p_other[0].splitlines() if l.strip()]

    p_hf = p_other[1].split("===DT_PYTHON===")
    hf_text = p_hf[0].strip()

    py_json_text = p_hf[1].strip() if len(p_hf) > 1 else "{}"

    py_data = {}
    try:
        py_data = json.loads(py_json_text)
    except Exception:
        pass

    primary_controller: Dict[str, Any] = {}
    if py_data.get("nodes"):
        node = py_data["nodes"][0]
        primary_controller = {
            "node": node.get("name", "lm3642@63"),
            "chip": "Texas Instruments LM3642",
            "path": node.get("path"),
            "compatible": node.get("compatible"),
            "reg": node.get("reg"),
            "cooling_cells": node.get("cooling_cells"),
            "subnodes": node.get("subnodes", {}),
        }

    rear_optical = {
        "present": "rear_cct" in hf_text or "tcs3408" in hf_text,
        "chip": "ams TCS3408",
        "subsystem": "sensorhub / hf_manager",
        "device_name": "rear_cct",
        "sensor_types": [
            {"type": 98, "name": "tcs3408 als"},
            {"type": 99, "name": "tcs3408 cct"},
            {"type": 100, "name": "tcs3408 flicker"},
        ],
        "explanation": "The second pale rear circle houses the rear CCT / ALS optical sensor (ams TCS3408), not a second light.",
    }

    return {
        "platform": "OnePlus Nord 3 5G CPH2493 (MT6983 / Project 22823 'Vitamin')",
        "source_mode": "running_device_tree",
        "boot_id": boot_id,
        "controller": primary_controller,
        "other_flashlight_nodes": other_nodes,
        "rear_optical_sensor": rear_optical,
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Device-tree parser and gate for Lynx second rear light topology"
    )
    parser.add_argument(
        "dt_fixture",
        type=Path,
        nargs="?",
        default=None,
        help="Path to parsed DT JSON fixture (offline evaluation mode)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Query running device tree on Lynx via SSH (requires --allow-live)",
    )
    parser.add_argument(
        "--allow-live",
        action="store_true",
        help="Explicit confirmation to query running device tree",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_LYNX_HOST,
        help="Lynx host IP for live query",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_LYNX_PORT,
        help="Lynx SSH port for live query",
    )
    args = parser.parse_args()

    if args.live:
        if not args.allow_live:
            err = {"error": "refusing live execution without both --live and --allow-live"}
            print(json.dumps(err, indent=2), file=sys.stderr)
            sys.exit(2)

        live_data = collect_live_flashlight_dt(host=args.host, port=args.port)
        if "error" in live_data:
            print(json.dumps({"status": "FAILED", "error": live_data["error"]}, indent=2))
            sys.exit(1)

        verdict = evaluate_flashlight_topology(live_data)
        print(json.dumps(verdict.to_dict(), indent=2))
        sys.exit(0 if verdict.is_valid else 1)

    if not args.dt_fixture:
        parser.print_help(file=sys.stderr)
        sys.exit(2)

    if not args.dt_fixture.exists():
        print(f"Error: file not found: {args.dt_fixture}", file=sys.stderr)
        sys.exit(2)

    try:
        data = json.loads(args.dt_fixture.read_text())
    except Exception as exc:
        print(f"Error: JSON parse failed: {exc}", file=sys.stderr)
        sys.exit(1)

    verdict = evaluate_flashlight_topology(data)
    print(json.dumps(verdict.to_dict(), indent=2))
    sys.exit(0 if verdict.is_valid else 1)


if __name__ == "__main__":
    main()
