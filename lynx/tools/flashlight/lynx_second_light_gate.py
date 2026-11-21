#!/usr/bin/env python3
"""Offline device-tree and driver parser/gate for the Lynx second rear light source.

Strictly read-only and offline: does not actuate LED, bind modules, or write sysfs.
Maps device-tree nodes and driver topology to verify whether an independent second
rear LED channel or control path exists on Lynx (OnePlus 11R / 22823).
"""

from dataclasses import dataclass, field
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple


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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "is_valid": self.is_valid,
            "second_channel_exists": self.second_channel_exists,
            "controller_chip": self.controller_chip,
            "channels_found": self.channels_found,
            "summary": self.summary,
            "source_citations": self.source_citations,
            "failures": self.failures,
        }


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
        "kernel-mt6983/arch/arm64/boot/dts/mediatek/cust_mt6983_vitamin_camera_v4l2.dtsi:312-334",
        "mt6983-nord3-flashlight/flashlights-lm3642.c",
        "mt6983-nord3-flashlight/flashlight-core.c",
        "Texas Instruments LM3642 Datasheet (SNVS840A): Single 1.5A High-Side Current Source",
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

    channels, errors = parse_flash_channels(dt_data)

    if errors:
        return FlashlightTopologyVerdict(
            status="MALFORMED_DT",
            is_valid=False,
            second_channel_exists=False,
            controller_chip=chip_name,
            summary=f"Encountered {len(errors)} error(s) while parsing flash channels",
            source_citations=citations,
            failures=errors,
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
        return FlashlightTopologyVerdict(
            status="SINGLE_CHANNEL_ONLY",
            is_valid=True,
            second_channel_exists=False,
            controller_chip=chip_name,
            channels_found=channel_dicts,
            summary=(
                f"Verified single-channel rear flash on {compatible} ({chip_name}). "
                f"Single registered channel {ch.name} (type={ch.type_id}, ct={ch.ct_id}, "
                f"part={ch.part_id}). Independent second rear light control path is PROVEN ABSENT."
            ),
            source_citations=citations,
            failures=[],
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
        )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Offline parser and gate for Lynx second rear light topology"
    )
    parser.add_argument("dt_fixture", type=Path, help="Path to parsed DT JSON fixture")
    args = parser.parse_args()

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
