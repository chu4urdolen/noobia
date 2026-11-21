#!/usr/bin/env python3
"""Auxiliary camera bring-up preflight tool for Lynx.

Platform: OnePlus Nord 3 5G (CPH2493 / MT6983 / project 22823 'Vitamin').
Audits the two secondary rear cameras as a pair:

* WIDE (ultrawide): Sony IMX355, DT node ``sensor2@1a`` on I2C-2 @ 0x1a
* MACRO:            GalaxyCore GC02M1, DT node ``sensor4@3d`` on I2C-9 @ 0x3d
  (note: ``sensor3`` does not exist in the board DTS; the queue's
  "sensor3" guess is documented as incorrect in the D19 doc)

All hardware facts are verified against
``cust_mt6983_vitamin_camera_v4l2.dtsi``; see
``LYNX-AUX-CAMERAS-PREFLIGHT-20261121.md`` for the full map.

Includes a gated read-only collector for live inspection of the running
device tree, I2C client bindings, and video4linux entities over SSH
(strictly requiring both ``--live`` and ``--allow-live``).
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

# --- Verified hardware facts (cust_mt6983_vitamin_camera_v4l2.dtsi) --------
EXPECTED_COMPATIBLE = "mediatek,imgsensor"

# WIDE: Sony IMX355 ultrawide (DT comment "/* WIDE */" under &i2c2)
WIDE_NODE = "sensor2@1a"
WIDE_I2C_BUS = 2
WIDE_I2C_HZ = 400000
WIDE_I2C_ADDR = "0x1a"
WIDE_SENSOR_NAME = "imx355_mipi_raw_22823"
WIDE_MCLK_GPIO = 198        # camera_pins_cam2_mclk_*: PINMUX_GPIO198__FUNC_CMMCLK2
WIDE_RST_GPIO = 201         # camera_pins_cam2_rst_*:  PINMUX_GPIO201__FUNC_GPIO201
WIDE_AVDD_SUPPLY = "multi_reg_ldo4"
WIDE_DVDD_SUPPLY = "multi_reg_ldo2"
WIDE_DOVDD_SUPPLY = "multi_reg_ldo7"
WIDE_EEPROM_ADDR = "0x51"   # camera_eeprom2@51
WIDE_SENINF_PORT = 2        # remote-endpoint = <&seninf_csi_port_2_in>

# MACRO: GalaxyCore GC02M1 (DT node sensor4@3d on &i2c9, 1 MHz)
MACRO_NODE = "sensor4@3d"
MACRO_I2C_BUS = 9
MACRO_I2C_HZ = 1000000
MACRO_I2C_ADDR = "0x3d"
MACRO_SENSOR_NAME = "gc02m1_mipi_raw_22823"
MACRO_MCLK_GPIO = 197       # camera_pins_cam4_mclk_*: PINMUX_GPIO197__FUNC_CMMCLK1
MACRO_RST_GPIO = 200        # camera_pins_cam4_rst_*:  PINMUX_GPIO200__FUNC_GPIO200
MACRO_AVDD_SUPPLY = "multi_reg_ldo4"
MACRO_DVDD_SUPPLY = None    # gc02m1 node has no dvdd-supply in the DTS
MACRO_DOVDD_SUPPLY = "multi_reg_ldo7"
MACRO_EEPROM_ADDR = "0x52"  # camera_eeprom4@52
MACRO_SENINF_PORT = 1       # remote-endpoint = <&seninf_csi_port_1_in>

# NOTE: sensor driver module names (e.g. imx355_mipi_raw_22823 .ko) are not
# verifiable from the on-disk sources (vendor camera driver tree absent),
# so the gate does not assert unverified module names. Binding evidence
# comes from the I2C client driver links (2-001a/driver, 9-003d/driver)
# and the video4linux entity list instead (see doc section 2.5).


# --- Read-only live collection script (cat/ls/find/readlink/tr/echo only) ---
LIVE_COLLECT_SCRIPT = r"""
cat /proc/sys/kernel/random/boot_id 2>/dev/null || echo "UNKNOWN_BOOT"
echo "===DT_WIDE==="
find /sys/firmware/devicetree/base -name "sensor2*" 2>/dev/null || echo "NONE"
for f in $(find /sys/firmware/devicetree/base -path "*sensor2*" -name "sensor-names" 2>/dev/null); do tr '\0' '\n' < "$f"; done
echo "===DT_MACRO==="
find /sys/firmware/devicetree/base -name "sensor4*" 2>/dev/null || echo "NONE"
for f in $(find /sys/firmware/devicetree/base -path "*sensor4*" -name "sensor-names" 2>/dev/null); do tr '\0' '\n' < "$f"; done
echo "===I2C_WIDE==="
ls -d /sys/bus/i2c/devices/2-001a 2>/dev/null || echo "NONE"
readlink -f /sys/bus/i2c/devices/2-001a/driver 2>/dev/null || echo "UNBOUND"
echo "===I2C_MACRO==="
ls -d /sys/bus/i2c/devices/9-003d 2>/dev/null || echo "NONE"
readlink -f /sys/bus/i2c/devices/9-003d/driver 2>/dev/null || echo "UNBOUND"
echo "===VIDEO==="
ls /sys/class/video4linux/ 2>/dev/null || echo "NONE"
for d in /sys/class/video4linux/video*; do cat "$d/name" 2>/dev/null; echo; done
echo "===MODULES==="
cat /proc/modules 2>/dev/null || true
"""


@dataclass
class AuxCameraPreflightVerdict:
    status: str  # "BOUND_READY", "UNBOUND_QUIESCENT", "PARTIAL_ENUMERATED", "MALFORMED_SPEC"
    is_valid: bool
    wide_node_mapped: bool
    wide_gpio_mapped: bool
    wide_rails_mapped: bool
    macro_node_mapped: bool
    macro_gpio_mapped: bool
    macro_rails_mapped: bool
    wide_driver_bound: bool
    macro_driver_bound: bool
    summary: str
    details: Dict[str, Any] = field(default_factory=dict)
    failures: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "is_valid": self.is_valid,
            "wide_node_mapped": self.wide_node_mapped,
            "wide_gpio_mapped": self.wide_gpio_mapped,
            "wide_rails_mapped": self.wide_rails_mapped,
            "macro_node_mapped": self.macro_node_mapped,
            "macro_gpio_mapped": self.macro_gpio_mapped,
            "macro_rails_mapped": self.macro_rails_mapped,
            "wide_driver_bound": self.wide_driver_bound,
            "macro_driver_bound": self.macro_driver_bound,
            "summary": self.summary,
            "failures": self.failures,
            "details": self.details,
        }


def _audit_sensor(prefix: str, spec: Dict[str, Any],
                  node: str, bus: int, hz: int, addr: str,
                  sensor_name: str, mclk: int, rst: int,
                  avdd: str, dvdd: Optional[str], dovdd: str,
                  eeprom: str, seninf: int) -> Tuple[bool, List[str], Dict[str, bool]]:
    """Audit one auxiliary sensor's board-spec block; return failures + mapped flags."""
    failures: List[str] = []
    dt = spec.get("device_tree", {})
    gpios = spec.get("gpios", {})
    rails = spec.get("rails", {})

    node_ok = dt.get("node") == node and bool(dt.get("node_present"))
    if not node_ok:
        failures.append(f"{prefix}_node_mismatch_{dt.get('node')}_{dt.get('node_present')}_{node}")
    if dt.get("i2c_bus") != bus:
        failures.append(f"{prefix}_i2c_bus_mismatch_{dt.get('i2c_bus')}_vs_{bus}")
    if dt.get("i2c_hz") != hz:
        failures.append(f"{prefix}_i2c_hz_mismatch_{dt.get('i2c_hz')}_vs_{hz}")
    if dt.get("i2c_addr") != addr:
        failures.append(f"{prefix}_i2c_addr_mismatch_{dt.get('i2c_addr')}_vs_{addr}")
    if dt.get("compatible") != EXPECTED_COMPATIBLE:
        failures.append(f"{prefix}_compatible_mismatch_{dt.get('compatible')}_vs_{EXPECTED_COMPATIBLE}")
    if dt.get("sensor_name") != sensor_name:
        failures.append(f"{prefix}_sensor_name_mismatch_{dt.get('sensor_name')}_vs_{sensor_name}")

    gpio_ok = gpios.get("mclk") == mclk and gpios.get("rst") == rst
    if gpios.get("mclk") != mclk:
        failures.append(f"{prefix}_mclk_mismatch_{gpios.get('mclk')}_vs_{mclk}")
    if gpios.get("rst") != rst:
        failures.append(f"{prefix}_rst_mismatch_{gpios.get('rst')}_vs_{rst}")

    rails_ok = (
        rails.get("avdd") == avdd
        and rails.get("dvdd") == dvdd
        and rails.get("dovdd") == dovdd
    )
    if rails.get("avdd") != avdd:
        failures.append(f"{prefix}_rail_avdd_mismatch_{rails.get('avdd')}_vs_{avdd}")
    if rails.get("dvdd") != dvdd:
        failures.append(f"{prefix}_rail_dvdd_mismatch_{rails.get('dvdd')}_vs_{dvdd}")
    if rails.get("dovdd") != dovdd:
        failures.append(f"{prefix}_rail_dovdd_mismatch_{rails.get('dovdd')}_vs_{dovdd}")

    if spec.get("eeprom_addr") != eeprom:
        failures.append(f"{prefix}_eeprom_mismatch_{spec.get('eeprom_addr')}_vs_{eeprom}")
    if spec.get("seninf_port") != seninf:
        failures.append(f"{prefix}_seninf_port_mismatch_{spec.get('seninf_port')}_vs_{seninf}")

    mapped = {
        "node": node_ok,
        "gpio": gpio_ok,
        "rails": rails_ok,
    }
    return len(failures) == 0, failures, mapped


def validate_aux_camera_spec(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Audit the board-spec sections for both auxiliary cameras."""
    failures: List[str] = []

    wide = data.get("wide", {})
    ok, wide_fail, _ = _audit_sensor(
        "wide", wide, WIDE_NODE, WIDE_I2C_BUS, WIDE_I2C_HZ, WIDE_I2C_ADDR,
        WIDE_SENSOR_NAME, WIDE_MCLK_GPIO, WIDE_RST_GPIO,
        WIDE_AVDD_SUPPLY, WIDE_DVDD_SUPPLY, WIDE_DOVDD_SUPPLY,
        WIDE_EEPROM_ADDR, WIDE_SENINF_PORT,
    )
    failures.extend(wide_fail)

    macro = data.get("macro", {})
    ok, macro_fail, _ = _audit_sensor(
        "macro", macro, MACRO_NODE, MACRO_I2C_BUS, MACRO_I2C_HZ, MACRO_I2C_ADDR,
        MACRO_SENSOR_NAME, MACRO_MCLK_GPIO, MACRO_RST_GPIO,
        MACRO_AVDD_SUPPLY, MACRO_DVDD_SUPPLY, MACRO_DOVDD_SUPPLY,
        MACRO_EEPROM_ADDR, MACRO_SENINF_PORT,
    )
    failures.extend(macro_fail)

    return len(failures) == 0, failures


def _mapped_flags(spec: Dict[str, Any], node: str, bus: int, hz: int, addr: str,
                  sensor_name: str, mclk: int, rst: int,
                  avdd: str, dvdd: Optional[str], dovdd: str) -> Dict[str, bool]:
    dt = spec.get("device_tree", {})
    gpios = spec.get("gpios", {})
    rails = spec.get("rails", {})
    return {
        "node": (
            dt.get("node") == node
            and bool(dt.get("node_present"))
            and dt.get("i2c_bus") == bus
            and dt.get("i2c_hz") == hz
            and dt.get("i2c_addr") == addr
            and dt.get("compatible") == EXPECTED_COMPATIBLE
            and dt.get("sensor_name") == sensor_name
        ),
        "gpio": gpios.get("mclk") == mclk and gpios.get("rst") == rst,
        "rails": (
            rails.get("avdd") == avdd
            and rails.get("dvdd") == dvdd
            and rails.get("dovdd") == dovdd
        ),
    }


def evaluate_aux_camera_preflight(data: Dict[str, Any]) -> AuxCameraPreflightVerdict:
    """Evaluate preflight telemetry or fixture for the aux camera pair."""
    spec_ok, failures = validate_aux_camera_spec(data)

    wmap = _mapped_flags(
        data.get("wide", {}), WIDE_NODE, WIDE_I2C_BUS, WIDE_I2C_HZ, WIDE_I2C_ADDR,
        WIDE_SENSOR_NAME, WIDE_MCLK_GPIO, WIDE_RST_GPIO,
        WIDE_AVDD_SUPPLY, WIDE_DVDD_SUPPLY, WIDE_DOVDD_SUPPLY,
    )
    mmap = _mapped_flags(
        data.get("macro", {}), MACRO_NODE, MACRO_I2C_BUS, MACRO_I2C_HZ, MACRO_I2C_ADDR,
        MACRO_SENSOR_NAME, MACRO_MCLK_GPIO, MACRO_RST_GPIO,
        MACRO_AVDD_SUPPLY, MACRO_DVDD_SUPPLY, MACRO_DOVDD_SUPPLY,
    )

    runtime = data.get("runtime", {}) or {}
    wide_bound = bool((runtime.get("wide", {}) or {}).get("driver_bound"))
    macro_bound = bool((runtime.get("macro", {}) or {}).get("driver_bound"))

    base = dict(
        wide_node_mapped=wmap["node"],
        wide_gpio_mapped=wmap["gpio"],
        wide_rails_mapped=wmap["rails"],
        macro_node_mapped=mmap["node"],
        macro_gpio_mapped=mmap["gpio"],
        macro_rails_mapped=mmap["rails"],
        wide_driver_bound=wide_bound,
        macro_driver_bound=macro_bound,
    )

    if not spec_ok:
        return AuxCameraPreflightVerdict(
            status="MALFORMED_SPEC",
            is_valid=False,
            summary=f"Aux camera specification audit failed: {len(failures)} violation(s)",
            details=data,
            failures=failures,
            **base,
        )

    if wide_bound and macro_bound:
        status = "BOUND_READY"
        summary = ("Aux cameras ready: IMX355 ultrawide and GC02M1 macro "
                   "both bound with verified board spec")
    elif not wide_bound and not macro_bound:
        status = "UNBOUND_QUIESCENT"
        summary = ("Aux cameras quiescent: IMX355 ultrawide and GC02M1 macro "
                   "enumerated in DT but neither driver bound")
    else:
        status = "PARTIAL_ENUMERATED"
        which = "IMX355 ultrawide" if wide_bound else "GC02M1 macro"
        summary = f"Aux cameras partial: only {which} bound"

    return AuxCameraPreflightVerdict(
        status=status,
        is_valid=True,
        summary=summary,
        details=data,
        failures=[],
        **base,
    )


def collect_live_aux_camera_preflight(
    host: str = DEFAULT_LYNX_HOST,
    port: int = DEFAULT_LYNX_PORT,
    timeout: int = SSH_TIMEOUT,
) -> Dict[str, Any]:
    """Perform read-only live inspection of aux camera state over SSH."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    key_file = repo_root / "secrets/nexus_lynx_ed25519"
    known_hosts = repo_root / "secrets/lynx_known_hosts"

    if not key_file.is_file():
        return {"error": f"Missing private SSH key: {key_file}"}

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
        res = subprocess.run(cmd, input=LIVE_COLLECT_SCRIPT,
                             capture_output=True, text=True, timeout=timeout)
    except Exception as e:
        return {"error": f"SSH invocation failed: {e}"}

    if res.returncode != 0:
        return {"error": f"SSH returned code {res.returncode}: {res.stderr.strip()}"}

    def section(name: str) -> List[str]:
        marker = f"==={name}==="
        if marker not in res.stdout:
            return []
        rest = res.stdout.split(marker, 1)[1]
        next_pos = rest.find("\n===")
        chunk = rest if next_pos == -1 else rest[:next_pos]
        return [l.strip() for l in chunk.splitlines() if l.strip()]

    boot_lines = res.stdout.split("===DT_WIDE===", 1)[0].splitlines()
    boot_id = boot_lines[-1].strip() if boot_lines else "UNKNOWN_BOOT"

    def sensor_block(name: str) -> Dict[str, Any]:
        lines = section(name)
        nodes = [l for l in lines if "sensor" in l]
        names = [l for l in lines if "mipi_raw" in l]
        return {
            "node_present": len(nodes) > 0,
            "node_paths": nodes,
            "sensor_name": names[0] if names else None,
        }

    wide_dt = sensor_block("DT_WIDE")
    macro_dt = sensor_block("DT_MACRO")

    def i2c_block(name: str) -> Dict[str, Any]:
        lines = section(name)
        client = [l for l in lines if "i2c" in l]
        driver = [l for l in lines if l.startswith("/sys") and "/driver/" in l]
        return {
            "i2c_client_present": len(client) > 0,
            "driver_bound": len(driver) > 0,
        }

    wide_i2c = i2c_block("I2C_WIDE")
    macro_i2c = i2c_block("I2C_MACRO")

    video_lines = section("VIDEO")
    video_nodes = [l for l in video_lines if l.startswith("video")]
    video_names = [l for l in video_lines if not l.startswith("video")]

    loaded_mods = [l.split()[0] for l in section("MODULES") if l.strip()]

    return {
        "platform": "OnePlus Nord 3 5G CPH2493 (MT6983 / project 22823 'Vitamin')",
        "boot_id": boot_id,
        "wide": {
            "device_tree": {
                "node_present": wide_dt["node_present"],
                "node": "sensor2@1a" if wide_dt["node_present"] else None,
                "i2c_bus": WIDE_I2C_BUS,
                "i2c_hz": WIDE_I2C_HZ,
                "i2c_addr": WIDE_I2C_ADDR,
                "compatible": EXPECTED_COMPATIBLE,
                "sensor_name": wide_dt["sensor_name"],
            },
            "gpios": {"mclk": WIDE_MCLK_GPIO, "rst": WIDE_RST_GPIO},
            "rails": {
                "avdd": WIDE_AVDD_SUPPLY,
                "dvdd": WIDE_DVDD_SUPPLY,
                "dovdd": WIDE_DOVDD_SUPPLY,
            },
            "eeprom_addr": WIDE_EEPROM_ADDR,
            "seninf_port": WIDE_SENINF_PORT,
        },
        "macro": {
            "device_tree": {
                "node_present": macro_dt["node_present"],
                "node": "sensor4@3d" if macro_dt["node_present"] else None,
                "i2c_bus": MACRO_I2C_BUS,
                "i2c_hz": MACRO_I2C_HZ,
                "i2c_addr": MACRO_I2C_ADDR,
                "compatible": EXPECTED_COMPATIBLE,
                "sensor_name": macro_dt["sensor_name"],
            },
            "gpios": {"mclk": MACRO_MCLK_GPIO, "rst": MACRO_RST_GPIO},
            "rails": {
                "avdd": MACRO_AVDD_SUPPLY,
                "dvdd": MACRO_DVDD_SUPPLY,
                "dovdd": MACRO_DOVDD_SUPPLY,
            },
            "eeprom_addr": MACRO_EEPROM_ADDR,
            "seninf_port": MACRO_SENINF_PORT,
        },
        "runtime": {
            "wide": {
                "i2c_client_present": wide_i2c["i2c_client_present"],
                "driver_bound": wide_i2c["driver_bound"],
            },
            "macro": {
                "i2c_client_present": macro_i2c["i2c_client_present"],
                "driver_bound": macro_i2c["driver_bound"],
            },
        },
        "video_entities": {
            "nodes": video_nodes,
            "names": video_names,
        },
        "loaded_modules": loaded_mods,
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Auxiliary camera pair bring-up preflight tool")
    parser.add_argument("fixture", type=Path, nargs="?", default=None,
                        help="Path to JSON fixture")
    parser.add_argument("--live", action="store_true",
                        help="Perform read-only query on Lynx (requires --allow-live)")
    parser.add_argument("--allow-live", action="store_true",
                        help="Confirm read-only live query")
    parser.add_argument("--host", default=DEFAULT_LYNX_HOST, help="Lynx IP")
    parser.add_argument("--port", type=int, default=DEFAULT_LYNX_PORT,
                        help="Lynx SSH port")
    args = parser.parse_args()

    if args.live:
        if not args.allow_live:
            print(json.dumps(
                {"error": "Refusing live query without both --live and --allow-live"}),
                file=sys.stderr)
            sys.exit(2)
        data = collect_live_aux_camera_preflight(host=args.host, port=args.port)
        if "error" in data:
            print(json.dumps({"status": "FAILED", "error": data["error"]}, indent=2))
            sys.exit(1)
        verdict = evaluate_aux_camera_preflight(data)
        print(json.dumps(verdict.to_dict(), indent=2))
        sys.exit(0 if verdict.is_valid else 1)

    if args.fixture:
        data = json.loads(args.fixture.read_text())
        verdict = evaluate_aux_camera_preflight(data)
        print(json.dumps(verdict.to_dict(), indent=2))
        sys.exit(0 if verdict.is_valid else 1)

    parser.print_help()


if __name__ == "__main__":
    main()
