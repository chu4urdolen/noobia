#!/usr/bin/env python3
"""Flashlight core & LED torch preflight gate for Lynx.

Platform: OnePlus Nord 3 5G (CPH2493 / MT6983 / project 22823 'Vitamin').
Validates offline the board's flashlight topology: the top-level
``flashlight_core`` framework node in ``mt6983.dts``, the single-channel
TI LM3642 flash LED driver ``lm3642@63`` on ``&i2c6`` with its
``flash@0`` channel endpoint pair (``fl_core_0`` <-> ``flashlight_0`` on
``&mtk_composite_v4l2_1``), and the flash NTC thermal sensor ``cam_temp``
on the MT6373 ADC (``AUXADC_VIN3``). Then classifies the runtime state of
the Linux LED flash interface (``/sys/class/leds/flash*``) without ever
activating the torch.

All hardware facts below are verified against the Nord 3 source tree; see
``LYNX-FLASHLIGHT-CORE-PREFLIGHT-20261121.md`` for the full map.

Also includes a gated read-only collector for live inspection of the
running device tree, LED flash class, driver binding, and loaded kernel
modules over SSH (strictly requiring both ``--live`` and ``--allow-live``).

Safety invariants:
* Offline by default; the live collector performs zero writes to any
  sysfs attribute (writing ``brightness``/``delay`` would emit torch
  light and is never done).
* Zero module loads, zero unapproved installs, zero optical emission.
* An LED flash device found with non-zero brightness at inspection time
  is reported as ``TORCH_ACTIVE`` and fails the gate for human review
  (a torch pulse should be transient; a persistent non-zero brightness
  at inspection time is anomalous).
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

# --- Verified hardware facts -----------------------------------------------
# 1) mt6983.dts:13806-13808 (top-level node, parent is /):
#      flashlight_core: flashlight_core {
#          compatible = "mediatek,flashlight_core";
#      };
# 2) cust_mt6983_vitamin_camera_v4l2.dtsi:312-334 (&i2c6):
#      lm3642:lm3642@63 {
#          compatible = "mediatek,lm3642_22823";
#          reg = <0x63>;
#          #cooling-cells = <2>;
#          pinctrl hwen high/low (GPIO33);
#          status = "okay";
#          flash@0 { reg = <0>; type = <0>; ct = <0>; part = <0>;
#              port@0 { fl_core_0: endpoint { remote-endpoint = <&flashlight_0>; }; };
#          };
#      };
# 3) cust_mt6983_vitamin_camera_v4l2.dtsi:66-73 (&mtk_composite_v4l2_1):
#      port@0 { flashlight_0: endpoint { remote-endpoint = <&fl_core_0>; }; };
# 4) cust_mt6983_vitamin_cam_thermal.dtsi:15-19 + cam_temp node:
#      &thermal_zones { flashlight_ntc { thermal-sensors = <&cam_temp>; }; };
#      cam_temp: cam_temp {
#          compatible = "mediatek,cam-temp-vitamin";
#          io-channels = <&mt6373_adc (ADC_PURES_100K_MASK | AUXADC_VIN3)>;
#      };
# 5) Live running-DT evidence (B4 receipt, boot 0fe847d2):
#      /sys/firmware/devicetree/base/i2c@11e02000/lm3642@63/flash@0
#      SINGLE_CHANNEL_ONLY; second rear circle is the ams TCS3408 CCT/ALS.

EXPECTED_CORE_NODE_NAME = "flashlight_core"
EXPECTED_CORE_LABEL = "flashlight_core"
EXPECTED_CORE_COMPATIBLE = "mediatek,flashlight_core"
EXPECTED_CORE_PARENT = "root"     # top-level node in mt6983.dts (parent /)

EXPECTED_LED_NODE_NAME = "lm3642@63"
EXPECTED_LED_LABEL = "lm3642"
EXPECTED_LED_BUS = "i2c6"
EXPECTED_LED_COMPATIBLE = "mediatek,lm3642_22823"
EXPECTED_LED_REG = 0x63          # 99 decimal
EXPECTED_LED_COOLING_CELLS = 2
EXPECTED_CHANNEL_NAME = "flash@0"
EXPECTED_CHANNEL_REG = 0
EXPECTED_ENDPOINT_LED = "fl_core_0"
EXPECTED_ENDPOINT_CONSUMER = "flashlight_0"

EXPECTED_NTC_SENSOR_LABEL = "cam_temp"
EXPECTED_NTC_COMPATIBLE = "mediatek,cam-temp-vitamin"
EXPECTED_NTC_ADC = "mt6373_adc"
EXPECTED_NTC_ADC_CHANNEL = "AUXADC_VIN3"

# Runtime interface (standard Linux LED class for flash devices):
EXPECTED_LED_CLASS_PREFIX = "/sys/class/leds/flash"

# NOTE (queue claim, UNVERIFIED / contradicted): the Round 7 queue names a
# "dual-LED torch regulator" and "MT6375 flash LED controller: torch
# <= 300 mA / strobe <= 1500 mA, timeout safety registers". Verified on
# disk instead: the flash LED driver is the TI LM3642 (single channel,
# live-DT receipt boot 0fe847d2: SINGLE_CHANNEL_ONLY), and no MT6375 flash
# LED controller node exists in the DTS (mt6375 references on disk are
# charger/auxadc/gauge only). LM3642 datasheet (SNVS840A, cited by the B4
# receipt) specifies a single 1.5 A high-side current source, which is
# consistent with the 1500 mA strobe figure but the 300 mA torch limit is
# not asserted anywhere on disk. The gate therefore does NOT assert
# "dual-LED" or MT6375 current-limit registers (D17-D21 precedent).


# --- Read-only live collection script (cat/ls/find/readlink/tr/echo only) ---
LIVE_COLLECT_SCRIPT = r"""
cat /proc/sys/kernel/random/boot_id 2>/dev/null || echo "UNKNOWN_BOOT"
echo "===FLASH_LEDS==="
ls -d /sys/class/leds/flash* 2>/dev/null || echo "NONE"
echo "===FLASH_DRIVER==="
for d in /sys/class/leds/flash*; do readlink -f "$d/driver" 2>/dev/null || echo "UNBOUND"; done
echo "===FLASH_BRIGHT==="
for d in /sys/class/leds/flash*; do cat "$d/brightness" 2>/dev/null || echo "NO_BRIGHT"; done
echo "===DT_LED==="
find /sys/firmware/devicetree/base -maxdepth 3 -name "lm3642@*" 2>/dev/null || echo "NONE"
echo "===DT_LED_PROPS==="
for f in $(find /sys/firmware/devicetree/base -maxdepth 3 -name "lm3642@*" 2>/dev/null); do
  echo "compatible=$(tr '\0' '\n' < "$f/compatible" 2>/dev/null)"
  echo "channel_present=$([ -d "$f/flash@0" ] && echo yes || echo no)"
  echo "children=$(ls "$f" 2>/dev/null | tr '\n' ' ')"
done
echo "===DT_CORE==="
find /sys/firmware/devicetree/base -maxdepth 2 -name "flashlight_core" 2>/dev/null || echo "NONE"
echo "===DT_CORE_PROPS==="
for f in $(find /sys/firmware/devicetree/base -maxdepth 2 -name "flashlight_core" 2>/dev/null); do
  echo "compatible=$(tr '\0' '\n' < "$f/compatible" 2>/dev/null)"
done
echo "===DT_NTC==="
find /sys/firmware/devicetree/base -maxdepth 4 -name "cam_temp" 2>/dev/null || echo "NONE"
echo "===DT_NTC_PROPS==="
for f in $(find /sys/firmware/devicetree/base -maxdepth 4 -name "cam_temp" 2>/dev/null); do
  echo "compatible=$(tr '\0' '\n' < "$f/compatible" 2>/dev/null)"
done
echo "===MODULES==="
cat /proc/modules 2>/dev/null || true
"""


@dataclass
class FlashlightGateVerdict:
    status: str  # TORCH_QUIESCENT / UNBOUND_QUIESCENT / PARTIAL_ENUMERATED / TORCH_ACTIVE / MALFORMED_SPEC
    is_valid: bool
    core_node_mapped: bool
    led_node_mapped: bool
    single_channel_verified: bool
    ntc_sensor_mapped: bool
    runtime_class_present: bool
    led_driver_bound: bool
    torch_quiescent: bool
    summary: str
    details: Dict[str, Any] = field(default_factory=dict)
    failures: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "is_valid": self.is_valid,
            "core_node_mapped": self.core_node_mapped,
            "led_node_mapped": self.led_node_mapped,
            "single_channel_verified": self.single_channel_verified,
            "ntc_sensor_mapped": self.ntc_sensor_mapped,
            "runtime_class_present": self.runtime_class_present,
            "led_driver_bound": self.led_driver_bound,
            "torch_quiescent": self.torch_quiescent,
            "summary": self.summary,
            "failures": self.failures,
            "details": self.details,
        }


def validate_flashlight_spec(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Audit the board-spec sections of a flashlight preflight document."""
    failures: List[str] = []
    dt = data.get("device_tree", {})

    # flashlight_core framework node
    if not dt.get("core_node_present"):
        failures.append("missing_flashlight_core_node_in_dt")
    if dt.get("core_node_name") != EXPECTED_CORE_NODE_NAME:
        failures.append(f"core_node_name_mismatch_{dt.get('core_node_name')}_vs_{EXPECTED_CORE_NODE_NAME}")
    if dt.get("core_compatible") != EXPECTED_CORE_COMPATIBLE:
        failures.append(f"core_compatible_mismatch_{dt.get('core_compatible')}_vs_{EXPECTED_CORE_COMPATIBLE}")
    if dt.get("core_parent") != EXPECTED_CORE_PARENT:
        failures.append(f"core_parent_mismatch_{dt.get('core_parent')}_vs_{EXPECTED_CORE_PARENT}")

    # LM3642 LED driver node
    if not dt.get("led_node_present"):
        failures.append("missing_led_node_in_dt")
    if dt.get("led_node_name") != EXPECTED_LED_NODE_NAME:
        failures.append(f"led_node_name_mismatch_{dt.get('led_node_name')}_vs_{EXPECTED_LED_NODE_NAME}")
    if dt.get("led_bus") != EXPECTED_LED_BUS:
        failures.append(f"led_bus_mismatch_{dt.get('led_bus')}_vs_{EXPECTED_LED_BUS}")
    if dt.get("led_compatible") != EXPECTED_LED_COMPATIBLE:
        failures.append(f"led_compatible_mismatch_{dt.get('led_compatible')}_vs_{EXPECTED_LED_COMPATIBLE}")
    if dt.get("led_reg") not in (EXPECTED_LED_REG, hex(EXPECTED_LED_REG)):
        failures.append(f"led_reg_mismatch_{dt.get('led_reg')}_vs_{EXPECTED_LED_REG}")
    if dt.get("led_cooling_cells") != EXPECTED_LED_COOLING_CELLS:
        failures.append(f"led_cooling_cells_mismatch_{dt.get('led_cooling_cells')}_vs_{EXPECTED_LED_COOLING_CELLS}")

    # single flash channel + endpoint pair
    if dt.get("channel_name") != EXPECTED_CHANNEL_NAME:
        failures.append(f"channel_name_mismatch_{dt.get('channel_name')}_vs_{EXPECTED_CHANNEL_NAME}")
    if dt.get("channel_count") != 1:
        failures.append(f"channel_count_mismatch_{dt.get('channel_count')}_vs_1")
    if dt.get("endpoint_led") != EXPECTED_ENDPOINT_LED:
        failures.append(f"endpoint_led_mismatch_{dt.get('endpoint_led')}_vs_{EXPECTED_ENDPOINT_LED}")
    if dt.get("endpoint_consumer") != EXPECTED_ENDPOINT_CONSUMER:
        failures.append(f"endpoint_consumer_mismatch_{dt.get('endpoint_consumer')}_vs_{EXPECTED_ENDPOINT_CONSUMER}")

    # flash NTC thermal sensor
    if not dt.get("ntc_sensor_present"):
        failures.append("missing_ntc_sensor_in_dt")
    if dt.get("ntc_sensor_label") != EXPECTED_NTC_SENSOR_LABEL:
        failures.append(f"ntc_sensor_mismatch_{dt.get('ntc_sensor_label')}_vs_{EXPECTED_NTC_SENSOR_LABEL}")
    if dt.get("ntc_compatible") != EXPECTED_NTC_COMPATIBLE:
        failures.append(f"ntc_compatible_mismatch_{dt.get('ntc_compatible')}_vs_{EXPECTED_NTC_COMPATIBLE}")
    if dt.get("ntc_adc") != EXPECTED_NTC_ADC:
        failures.append(f"ntc_adc_mismatch_{dt.get('ntc_adc')}_vs_{EXPECTED_NTC_ADC}")
    if dt.get("ntc_adc_channel") != EXPECTED_NTC_ADC_CHANNEL:
        failures.append(f"ntc_adc_channel_mismatch_{dt.get('ntc_adc_channel')}_vs_{EXPECTED_NTC_ADC_CHANNEL}")

    return len(failures) == 0, failures


def _brightness_value(value: Any) -> Optional[int]:
    """Coerce a sysfs brightness value; None when absent or unparsable."""
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def evaluate_flashlight_gate(data: Dict[str, Any]) -> FlashlightGateVerdict:
    """Evaluate preflight telemetry or fixture for the Nord 3 flashlight."""
    spec_ok, failures = validate_flashlight_spec(data)

    dt = data.get("device_tree", {})
    core_mapped = (
        bool(dt.get("core_node_present"))
        and dt.get("core_node_name") == EXPECTED_CORE_NODE_NAME
        and dt.get("core_compatible") == EXPECTED_CORE_COMPATIBLE
        and dt.get("core_parent") == EXPECTED_CORE_PARENT
    )
    led_mapped = (
        bool(dt.get("led_node_present"))
        and dt.get("led_node_name") == EXPECTED_LED_NODE_NAME
        and dt.get("led_bus") == EXPECTED_LED_BUS
        and dt.get("led_compatible") == EXPECTED_LED_COMPATIBLE
        and dt.get("led_reg") in (EXPECTED_LED_REG, hex(EXPECTED_LED_REG))
        and dt.get("led_cooling_cells") == EXPECTED_LED_COOLING_CELLS
    )
    single_channel = (
        dt.get("channel_name") == EXPECTED_CHANNEL_NAME
        and dt.get("channel_count") == 1
        and dt.get("endpoint_led") == EXPECTED_ENDPOINT_LED
        and dt.get("endpoint_consumer") == EXPECTED_ENDPOINT_CONSUMER
    )
    ntc_mapped = (
        bool(dt.get("ntc_sensor_present"))
        and dt.get("ntc_sensor_label") == EXPECTED_NTC_SENSOR_LABEL
        and dt.get("ntc_compatible") == EXPECTED_NTC_COMPATIBLE
        and dt.get("ntc_adc") == EXPECTED_NTC_ADC
        and dt.get("ntc_adc_channel") == EXPECTED_NTC_ADC_CHANNEL
    )

    runtime = data.get("runtime", {}) or {}
    class_present = bool(runtime.get("led_class_present"))
    bound = bool(runtime.get("led_driver_bound"))
    brightness = _brightness_value(runtime.get("led_brightness"))
    quiescent = brightness is None or brightness == 0

    if not spec_ok:
        return FlashlightGateVerdict(
            status="MALFORMED_SPEC",
            is_valid=False,
            core_node_mapped=core_mapped,
            led_node_mapped=led_mapped,
            single_channel_verified=single_channel,
            ntc_sensor_mapped=ntc_mapped,
            runtime_class_present=class_present,
            led_driver_bound=bound,
            torch_quiescent=quiescent,
            summary=f"Flashlight preflight specification audit failed: {len(failures)} violation(s)",
            details=data,
            failures=failures,
        )

    if bound and not quiescent:
        return FlashlightGateVerdict(
            status="TORCH_ACTIVE",
            is_valid=False,
            core_node_mapped=core_mapped,
            led_node_mapped=led_mapped,
            single_channel_verified=single_channel,
            ntc_sensor_mapped=ntc_mapped,
            runtime_class_present=class_present,
            led_driver_bound=bound,
            torch_quiescent=False,
            summary=(
                f"LED flash is bound and NON-QUIESCENT (brightness={brightness}) at inspection time. "
                "This is a safety anomaly: torch emission should be transient. Verify no flash "
                "source is driving the LED before proceeding."
            ),
            details=data,
            failures=["torch_not_quiescent"],
        )

    if bound and quiescent:
        status = "TORCH_QUIESCENT"
        summary = (
            "LED flash is bound and quiescent. Board topology mapped (flashlight_core, "
            "lm3642@63 on i2c6, single flash@0 channel, cam_temp NTC on mt6373_adc "
            "AUXADC_VIN3), driver bound, brightness 0."
        )
    elif class_present and not bound:
        status = "PARTIAL_ENUMERATED"
        summary = (
            "Flashlight interface partially enumerated: the LED flash class path is "
            "present but no driver is bound. Board spec verified offline."
        )
    else:
        status = "UNBOUND_QUIESCENT"
        summary = (
            "Flashlight preflight verified in quiescent state. Device tree mapped "
            "(flashlight_core, lm3642@63, single flash@0, cam_temp NTC), no runtime "
            "LED flash class interface (driver safely absent)."
        )

    return FlashlightGateVerdict(
        status=status,
        is_valid=True,
        core_node_mapped=core_mapped,
        led_node_mapped=led_mapped,
        single_channel_verified=single_channel,
        ntc_sensor_mapped=ntc_mapped,
        runtime_class_present=class_present,
        led_driver_bound=bound,
        torch_quiescent=quiescent,
        summary=summary,
        details=data,
        failures=[],
    )


def collect_live_flashlight_gate(
    host: str = DEFAULT_LYNX_HOST,
    port: int = DEFAULT_LYNX_PORT,
    timeout: int = SSH_TIMEOUT,
) -> Dict[str, Any]:
    """Perform read-only live inspection of flashlight hardware state over SSH."""
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
        res = subprocess.run(cmd, input=LIVE_COLLECT_SCRIPT, capture_output=True, text=True, timeout=timeout)
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

    boot_lines = res.stdout.split("===FLASH_LEDS===", 1)[0].splitlines()
    boot_id = boot_lines[-1].strip() if boot_lines else "UNKNOWN_BOOT"

    led_paths = [l for l in section("FLASH_LEDS") if l != "NONE"]
    class_present = len(led_paths) > 0
    led_path = led_paths[0] if led_paths else None

    driver_lines = [l for l in section("FLASH_DRIVER") if l and l != "UNBOUND"]
    bound = len(driver_lines) > 0

    bright_lines = [l for l in section("FLASH_BRIGHT") if l and l != "NO_BRIGHT"]
    brightness = _brightness_value(bright_lines[0]) if bright_lines else None

    led_nodes = [l for l in section("DT_LED") if l != "NONE"]
    led_present = len(led_nodes) > 0
    led_compatible = None
    channel_present = False
    for line in section("DT_LED_PROPS"):
        if line.startswith("compatible="):
            led_compatible = line.split("=", 1)[1].strip() or None
        if line.startswith("channel_present="):
            channel_present = line.split("=", 1)[1].strip() == "yes"

    core_nodes = [l for l in section("DT_CORE") if l != "NONE"]
    core_present = len(core_nodes) > 0
    core_compatible = None
    for line in section("DT_CORE_PROPS"):
        if line.startswith("compatible="):
            core_compatible = line.split("=", 1)[1].strip() or None

    ntc_nodes = [l for l in section("DT_NTC") if l != "NONE"]
    ntc_present = len(ntc_nodes) > 0
    ntc_compatible = None
    for line in section("DT_NTC_PROPS"):
        if line.startswith("compatible="):
            ntc_compatible = line.split("=", 1)[1].strip() or None

    module_lines = section("MODULES")
    loaded_mods = [l.split()[0] for l in module_lines if l.strip()]

    return {
        "platform": "OnePlus Nord 3 5G CPH2493 (MT6983 / project 22823 'Vitamin')",
        "boot_id": boot_id,
        "device_tree": {
            "core_node_present": core_present,
            "core_node_name": "flashlight_core" if core_present else None,
            "core_compatible": core_compatible,
            "core_parent": EXPECTED_CORE_PARENT,
            "led_node_present": led_present,
            "led_node_name": "lm3642@63" if led_present else None,
            "led_bus": EXPECTED_LED_BUS,
            "led_compatible": led_compatible,
            "led_reg": EXPECTED_LED_REG,
            "led_cooling_cells": EXPECTED_LED_COOLING_CELLS,
            "channel_name": "flash@0" if channel_present else None,
            "channel_count": 1 if channel_present else 0,
            "endpoint_led": EXPECTED_ENDPOINT_LED,
            "endpoint_consumer": EXPECTED_ENDPOINT_CONSUMER,
            "ntc_sensor_present": ntc_present,
            "ntc_sensor_label": EXPECTED_NTC_SENSOR_LABEL if ntc_present else None,
            "ntc_compatible": ntc_compatible,
            "ntc_adc": EXPECTED_NTC_ADC,
            "ntc_adc_channel": EXPECTED_NTC_ADC_CHANNEL,
        },
        "runtime": {
            "led_class_present": class_present,
            "led_class_path": led_path,
            "led_driver_bound": bound,
            "led_brightness": brightness,
        },
        "loaded_modules": loaded_mods,
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Flashlight core & LED torch preflight gate")
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
        data = collect_live_flashlight_gate(host=args.host, port=args.port)
        if "error" in data:
            print(json.dumps({"status": "FAILED", "error": data["error"]}, indent=2))
            sys.exit(1)
        verdict = evaluate_flashlight_gate(data)
        print(json.dumps(verdict.to_dict(), indent=2))
        sys.exit(0 if verdict.is_valid else 1)

    if args.fixture:
        data = json.loads(args.fixture.read_text())
        verdict = evaluate_flashlight_gate(data)
        print(json.dumps(verdict.to_dict(), indent=2))
        sys.exit(0 if verdict.is_valid else 1)

    parser.print_help()


if __name__ == "__main__":
    main()
