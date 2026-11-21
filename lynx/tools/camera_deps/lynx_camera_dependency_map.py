#!/usr/bin/env python3
"""Offline camera dependency and failure map for Lynx camera sensors.

Compares the proven macro (GC02M1) and wide (IMX355) RAM-patched ISP routes with
the untested main (IMX890) and front (S5K3P9SP) sensors.
Preserves existing lynx_camera_gate.py restrictions and identifies the next
smallest offline gate for each sensor.
"""

from dataclasses import dataclass, field
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

# Import lynx_camera_gate to verify consistency
GATE_TOOL = Path(__file__).resolve().parent.parent / "lynx_camera_gate.py"
if str(GATE_TOOL.parent) not in sys.path:
    sys.path.insert(0, str(GATE_TOOL.parent))

try:
    import lynx_camera_gate
except ImportError:
    lynx_camera_gate = None


@dataclass(frozen=True)
class SensorDependencySpec:
    sensor: str
    role: str
    i2c_device: str
    subdev_node: str
    seninf_sink: str
    phy_bus: str
    cfa_architecture: str
    preview_geometry: str
    pixel_format: str
    vcm_actuator_present: bool
    eeprom_present: bool
    status_proven: str
    gate_decision: str
    next_smallest_offline_gate: str
    critical_dependencies: List[str]
    missing_evidence: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sensor": self.sensor,
            "role": self.role,
            "i2c_device": self.i2c_device,
            "subdev_node": self.subdev_node,
            "seninf_sink": self.seninf_sink,
            "phy_bus": self.phy_bus,
            "cfa_architecture": self.cfa_architecture,
            "preview_geometry": self.preview_geometry,
            "pixel_format": self.pixel_format,
            "vcm_actuator_present": self.vcm_actuator_present,
            "eeprom_present": self.eeprom_present,
            "status_proven": self.status_proven,
            "gate_decision": self.gate_decision,
            "next_smallest_offline_gate": self.next_smallest_offline_gate,
            "critical_dependencies": self.critical_dependencies,
            "missing_evidence": self.missing_evidence,
        }


# Canonical sensor specifications derived from OnePlus 11R 22823 device tree,
# vendor driver sources, and Lynx camera port history.
SENSOR_MAP: Dict[str, SensorDependencySpec] = {
    "GC02M1": SensorDependencySpec(
        sensor="GC02M1",
        role="rear_macro",
        i2c_device="9-003d",
        subdev_node="/dev/v4l-subdev4",
        seninf_sink="seninf-1",
        phy_bus="MIPI D-PHY (1 lane)",
        cfa_architecture="Single-cell Bayer (RGGB phase)",
        preview_geometry="1600x1200",
        pixel_format="BA81",
        vcm_actuator_present=False,
        eeprom_present=False,
        status_proven="PROVEN_OPTICAL_RAM",
        gate_decision="ALLOW_WHEN_OPTICALLY_VERIFIED",
        next_smallest_offline_gate="AEC/AGC exposure calibration curve and white-balance matrix",
        critical_dependencies=[
            "RAM-patched mtk-cam-isp (YUV-B IRQ gate + CAMSV s_power)",
            "Staged full lib3a.ccu under dummy filename in volatile RAM",
            "CAMSV-0 streaming link via seninf-1",
            "DMA-BUF heap buffer allocation with media requests",
            "Sensor power regulators (multi_reg_ldo4, multi_reg_ldo7)",
        ],
        missing_evidence=[
            "Factory white balance calibration data",
            "Continuous autofocus or lens movement (fixed-focus sensor)",
        ],
    ),
    "IMX355": SensorDependencySpec(
        sensor="IMX355",
        role="rear_wide",
        i2c_device="2-001a",
        subdev_node="/dev/v4l-subdev6",
        seninf_sink="seninf-2",
        phy_bus="MIPI D-PHY (4 lanes)",
        cfa_architecture="Single-cell Bayer (RGGB)",
        preview_geometry="3264x2448",
        pixel_format="BA81",
        vcm_actuator_present=False,
        eeprom_present=True,
        status_proven="PROVEN_FRAME_RAM",
        gate_decision="ALLOW_WHEN_OPTICALLY_VERIFIED",
        next_smallest_offline_gate="Offline contrast / exposure tuning to lift frame above black level 16",
        critical_dependencies=[
            "Dynamic route switch media-ctl descriptor '27:1->615:0[4]'",
            "7,990,296-byte DMA buffer setup (7,990,272 pixels + 24-byte CAMSV header)",
            "EEPROM calibration read at 2-0051",
            "RAM-patched mtk-cam-isp and staged lib3a.ccu",
        ],
        missing_evidence=[
            "Recognizable optical scene validation (frame currently at black baseline 16)",
            "Color target phase confirmation on wide lens",
        ],
    ),
    "IMX890": SensorDependencySpec(
        sensor="IMX890",
        role="rear_main",
        i2c_device="8-0036",
        subdev_node="/dev/v4l-subdev8",
        seninf_sink="seninf-3",
        phy_bus="MIPI C-PHY (trio-based symbol encoding)",
        cfa_architecture="Four-cell Quad Bayer (2x2 clustered color filters)",
        preview_geometry="4096x3072",
        pixel_format="QUAD_BAYER_UNTESTED",
        vcm_actuator_present=True,
        eeprom_present=True,
        status_proven="UNTESTED_HARDWARE_REFUSED",
        gate_decision="HARD_REFUSE",
        next_smallest_offline_gate="Offline buffer geometry & C-PHY seninf-3 configuration parser",
        critical_dependencies=[
            "Four-cell remosaic ISP algorithm or raw quad unpacking helper",
            "MIPI C-PHY clock calibration and csi_efuse2 trimming in seninf",
            "VCM actuator power & position initialization (main_af / main_af1)",
            "EEPROM factory lens calibration parsing (8-0050 / 8-0051)",
            "Dynamic media route to seninf-3 -> CAMSV / DIP pipeline",
        ],
        missing_evidence=[
            "Quad-to-Bayer software or hardware remosaic pipeline",
            "C-PHY clock and voltage regulator stabilization data",
            "Actuator holding current and lens rest position without crash",
            "Live sensor probe without YUV interrupt storm on main channel",
        ],
    ),
    "S5K3P9SP": SensorDependencySpec(
        sensor="S5K3P9SP",
        role="front",
        i2c_device="9-0010",
        subdev_node="/dev/v4l-subdev2",
        seninf_sink="seninf-0",
        phy_bus="MIPI D-PHY",
        cfa_architecture="Four-cell Tetracell (Samsung 2x2 color pattern)",
        preview_geometry="2320x1744",
        pixel_format="TETRACELL_UNTESTED",
        vcm_actuator_present=False,
        eeprom_present=False,
        status_proven="UNTESTED_HARDWARE_REFUSED",
        gate_decision="HARD_REFUSE",
        next_smallest_offline_gate="Offline Tetracell 2320x1744 buffer geometry & power sequence spec",
        critical_dependencies=[
            "Tetracell demosaicing / re-mosaic layout mapping",
            "Dedicated seninf-0 routing configuration",
            "Front PMIC supply sequence (dvdd, avdd, dovdd)",
            "CAMSV media link descriptor for /dev/v4l-subdev2",
        ],
        missing_evidence=[
            "Tetracell sensor mode register sequences",
            "Front sensor power-up sequence and reset GPIO behavior",
            "Buffer size and stride calculation for 2320x1744 four-cell format",
        ],
    ),
}


def build_camera_dependency_map() -> Dict[str, Any]:
    """Return the complete camera dependency, failure map, and gate comparison."""
    return {
        "platform": "OnePlus 11R 5G (Lynx / MT6895 / 22823)",
        "isp_core": "MediaTek ISP 7.1 (MT6983)",
        "proven_isp_patch": "camera-yuv-irq-build (YUV-B IRQ gate + CAMSV s_power)",
        "sensors": {k: v.to_dict() for k, v in SENSOR_MAP.items()},
        "gate_alignment_verified": True,
        "source_citations": [
            "kernel-mt6983/arch/arm64/boot/dts/mediatek/cust_mt6983_vitamin_camera_v4l2.dtsi",
            "sources/oneplus-nord3-sensor-power/imgsensor_hw.c",
            "sources/oneplus-nord3-sensor-power/mtk_cam-camsv.c",
            "linux-port/docs/LYNX-CAMERA-PORT-PLAN.md",
            "tools/lynx_camera_gate.py",
        ],
    }


def verify_camera_gate_alignment() -> Tuple[bool, List[str]]:
    """Assert that this dependency map is 100% aligned with lynx_camera_gate.py."""
    if lynx_camera_gate is None:
        return False, ["lynx_camera_gate module not found"]

    discrepancies: List[str] = []

    # Check GC02M1 allowed route
    gc_dec = lynx_camera_gate.evaluate_request(
        {
            "sensor": "GC02M1",
            "width": 1600,
            "height": 1200,
            "pixel_format": "BA81",
            "optically_verified": True,
        }
    )
    if gc_dec.decision != lynx_camera_gate.ALLOW:
        discrepancies.append(f"GC02M1 route refused by gate: {gc_dec.reason}")

    # Check IMX355 allowed route
    imx355_dec = lynx_camera_gate.evaluate_request(
        {
            "sensor": "IMX355",
            "width": 3264,
            "height": 2448,
            "pixel_format": "BA81",
            "optically_verified": True,
        }
    )
    if imx355_dec.decision != lynx_camera_gate.ALLOW:
        discrepancies.append(f"IMX355 route refused by gate: {imx355_dec.reason}")

    # Check IMX890 hard refuse
    imx890_dec = lynx_camera_gate.evaluate_request(
        {
            "sensor": "IMX890",
            "width": 4096,
            "height": 3072,
            "pixel_format": "BA81",
            "optically_verified": True,
        }
    )
    if imx890_dec.decision != lynx_camera_gate.REFUSE:
        discrepancies.append("IMX890 was not refused by gate")

    # Check S5K3P9SP hard refuse
    s5k_dec = lynx_camera_gate.evaluate_request(
        {
            "sensor": "S5K3P9SP",
            "width": 2320,
            "height": 1744,
            "pixel_format": "BA81",
            "optically_verified": True,
        }
    )
    if s5k_dec.decision != lynx_camera_gate.REFUSE:
        discrepancies.append("S5K3P9SP was not refused by gate")

    return len(discrepancies) == 0, discrepancies


def main() -> None:
    dep_map = build_camera_dependency_map()
    aligned, errs = verify_camera_gate_alignment()
    if not aligned:
        print(f"Error: alignment with lynx_camera_gate failed: {errs}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(dep_map, indent=2))


if __name__ == "__main__":
    main()
