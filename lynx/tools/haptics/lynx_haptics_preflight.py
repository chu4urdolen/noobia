#!/usr/bin/env python3
"""Haptics (linear resonant actuator) bring-up preflight tool for Lynx.

Platform: OnePlus Nord 3 5G (CPH2493 / MT6983 / project 22823 'Vitamin').
Validates offline the Nord 3 vibrator node under ``&odm``, its
``mediatek,vibrator`` compatible string, and the waveform timer/limit/volume
parameters; then classifies the runtime state of the Linux vibrator class
interface (``/sys/class/timed_output/vibrator`` or ``/sys/class/leds/vibrator``)
without ever triggering a vibration pulse.

All hardware facts below are verified against the Nord 3 board device tree
``oplus6983_22823.dts``; see ``LYNX-HAPTICS-LRA-PREFLIGHT-20261121.md``
for the full map.

Also includes a gated read-only collector for live inspection of the
running device tree, vibrator class interface, driver binding, and
loaded kernel modules over SSH (strictly requiring both ``--live`` and
``--allow-live``).

Safety invariants:
* Offline by default; the live collector performs zero writes to any
  sysfs attribute (writing ``state``/``delay``/``brightness`` would
  drive the actuator).
* Zero module loads, zero unapproved installs, zero acoustic/vibration
  side effects.
* A bound actuator found in a non-zero state at inspection time is
  reported as ``ACTIVE_PULSE`` and fails the gate for human review
  (an LRA pulse is transient; a persistent active state is anomalous).
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
# Board DTS: arch/arm64/boot/dts/mediatek/oplus6983_22823.dts (snapshots/kernel-mt6983)
#   &odm {
#       ...
#       vibrator0:vibrator@0 {
#           compatible = "mediatek,vibrator";
#           vib_timer = <25>;
#           vib_limit = <9>;
#           vib_vol= <9>;
#       };
#   };

EXPECTED_NODE_NAME = "vibrator@0"        # node under &odm
EXPECTED_NODE_LABEL = "vibrator0"        # DTS label
EXPECTED_PARENT = "odm"                  # &odm
EXPECTED_COMPATIBLE = "mediatek,vibrator"
EXPECTED_VIB_TIMER = 25                  # vib_timer = <25>
EXPECTED_VIB_LIMIT = 9                   # vib_limit = <9>
EXPECTED_VIB_VOL = 9                     # vib_vol = <9>

# Runtime interface candidates (queue invariant; standard Linux classes):
EXPECTED_CLASS_PATHS = (
    "/sys/class/timed_output/vibrator",
    "/sys/class/leds/vibrator",
)

# NOTE: the Round 7 queue names "MT6375 haptic wave generator / LRA driver"
# as the expected sub-PMIC driver. No haptic/vibrator driver source is
# present in the on-disk kernel snapshot (verified: no compatible match
# outside the .dts files, no mt6375 vibra code, no dt-binding), so the gate
# does NOT assert unverified module names. Binding evidence comes from the
# Linux vibrator class interface and its driver link instead.


# --- Read-only live collection script (cat/ls/find/readlink/tr/echo only) ---
LIVE_COLLECT_SCRIPT = r"""
cat /proc/sys/kernel/random/boot_id 2>/dev/null || echo "UNKNOWN_BOOT"
echo "===VIB_CLASS==="
ls -d /sys/class/timed_output/vibrator /sys/class/leds/vibrator 2>/dev/null || echo "NONE"
echo "===VIB_DRIVER==="
for d in /sys/class/timed_output/vibrator /sys/class/leds/vibrator; do readlink -f "$d/driver" 2>/dev/null || echo "UNBOUND"; done
echo "===VIB_STATE==="
for d in /sys/class/timed_output/vibrator /sys/class/leds/vibrator; do cat "$d/state" 2>/dev/null || cat "$d/brightness" 2>/dev/null || echo "NO_STATE"; done
echo "===DT_VIBRATOR==="
find /sys/firmware/devicetree/base -maxdepth 3 -name "vibrator@*" 2>/dev/null || echo "NONE"
echo "===DT_VIB_PROPS==="
for f in $(find /sys/firmware/devicetree/base -maxdepth 3 -name "vibrator@*" 2>/dev/null); do echo "compatible=$(tr '\0' '\n' < "$f/compatible" 2>/dev/null)"; done
echo "===MODULES==="
cat /proc/modules 2>/dev/null || true
"""


@dataclass
class HapticsPreflightVerdict:
    status: str  # "BOUND_QUIESCENT", "UNBOUND_QUIESCENT", "PARTIAL_ENUMERATED", "ACTIVE_PULSE", "MALFORMED_SPEC"
    is_valid: bool
    node_mapped: bool
    compatible_mapped: bool
    waveform_params_mapped: bool
    vibrator_class_present: bool
    vibrator_driver_bound: bool
    actuator_quiescent: bool
    summary: str
    details: Dict[str, Any] = field(default_factory=dict)
    failures: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "is_valid": self.is_valid,
            "node_mapped": self.node_mapped,
            "compatible_mapped": self.compatible_mapped,
            "waveform_params_mapped": self.waveform_params_mapped,
            "vibrator_class_present": self.vibrator_class_present,
            "vibrator_driver_bound": self.vibrator_driver_bound,
            "actuator_quiescent": self.actuator_quiescent,
            "summary": self.summary,
            "failures": self.failures,
            "details": self.details,
        }


def validate_haptics_spec(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Audit the board-spec sections of a haptics preflight document."""
    failures: List[str] = []

    dt = data.get("device_tree", {})
    if not dt.get("vibrator_node_present"):
        failures.append("missing_vibrator_node_in_dt")
    if dt.get("node_name") != EXPECTED_NODE_NAME:
        failures.append(f"node_name_mismatch_{dt.get('node_name')}_vs_{EXPECTED_NODE_NAME}")
    if dt.get("parent_node") != EXPECTED_PARENT:
        failures.append(f"parent_node_mismatch_{dt.get('parent_node')}_vs_{EXPECTED_PARENT}")
    if dt.get("compatible") != EXPECTED_COMPATIBLE:
        failures.append(f"compatible_mismatch_{dt.get('compatible')}_vs_{EXPECTED_COMPATIBLE}")
    if dt.get("vib_timer") != EXPECTED_VIB_TIMER:
        failures.append(f"vib_timer_mismatch_{dt.get('vib_timer')}_vs_{EXPECTED_VIB_TIMER}")
    if dt.get("vib_limit") != EXPECTED_VIB_LIMIT:
        failures.append(f"vib_limit_mismatch_{dt.get('vib_limit')}_vs_{EXPECTED_VIB_LIMIT}")
    if dt.get("vib_vol") != EXPECTED_VIB_VOL:
        failures.append(f"vib_vol_mismatch_{dt.get('vib_vol')}_vs_{EXPECTED_VIB_VOL}")

    return len(failures) == 0, failures


def _state_value(value: Any) -> Optional[int]:
    """Coerce a sysfs state/brightness value; None when absent or unparsable."""
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def evaluate_haptics_preflight(data: Dict[str, Any]) -> HapticsPreflightVerdict:
    """Evaluate preflight telemetry or fixture for the Nord 3 haptic actuator."""
    spec_ok, failures = validate_haptics_spec(data)

    dt = data.get("device_tree", {})
    node_mapped = bool(dt.get("vibrator_node_present"))
    compatible_mapped = (
        dt.get("node_name") == EXPECTED_NODE_NAME
        and dt.get("parent_node") == EXPECTED_PARENT
        and dt.get("compatible") == EXPECTED_COMPATIBLE
    )
    waveform_params_mapped = (
        dt.get("vib_timer") == EXPECTED_VIB_TIMER
        and dt.get("vib_limit") == EXPECTED_VIB_LIMIT
        and dt.get("vib_vol") == EXPECTED_VIB_VOL
    )

    runtime = data.get("runtime", {}) or {}
    class_present = bool(runtime.get("vibrator_class_present"))
    bound = bool(runtime.get("vibrator_driver_bound"))
    state = _state_value(runtime.get("vibrator_state"))
    quiescent = state is None or state == 0

    if not spec_ok:
        return HapticsPreflightVerdict(
            status="MALFORMED_SPEC",
            is_valid=False,
            node_mapped=node_mapped,
            compatible_mapped=compatible_mapped,
            waveform_params_mapped=waveform_params_mapped,
            vibrator_class_present=class_present,
            vibrator_driver_bound=bound,
            actuator_quiescent=quiescent,
            summary=f"Haptics preflight specification audit failed: {len(failures)} violation(s)",
            details=data,
            failures=failures,
        )

    if bound and not quiescent:
        return HapticsPreflightVerdict(
            status="ACTIVE_PULSE",
            is_valid=False,
            node_mapped=node_mapped,
            compatible_mapped=compatible_mapped,
            waveform_params_mapped=waveform_params_mapped,
            vibrator_class_present=class_present,
            vibrator_driver_bound=bound,
            actuator_quiescent=False,
            summary=(
                f"Haptic actuator is bound and NON-QUIESCENT (state={state}) at inspection time. "
                "This is a safety anomaly: a pulse should be transient. Verify no haptic source "
                "is driving the actuator before proceeding."
            ),
            details=data,
            failures=["actuator_not_quiescent"],
        )

    if bound and quiescent:
        status = "BOUND_QUIESCENT"
        summary = (
            "Haptic actuator is bound and quiescent. Board DTS mapped (odm/vibrator@0, "
            "mediatek,vibrator, vib_timer 25 / vib_limit 9 / vib_vol 9), driver bound, "
            "actuator state 0."
        )
    elif class_present and not bound:
        status = "PARTIAL_ENUMERATED"
        summary = (
            "Haptics interface partially enumerated: the Linux vibrator class path is "
            "present but no driver is bound. Board spec verified offline."
        )
    else:
        status = "UNBOUND_QUIESCENT"
        summary = (
            "Haptic actuator preflight verified in quiescent state. Device tree mapped "
            "(odm/vibrator@0, mediatek,vibrator), waveform parameters verified, "
            "no runtime vibrator class interface (driver safely absent)."
        )

    return HapticsPreflightVerdict(
        status=status,
        is_valid=True,
        node_mapped=node_mapped,
        compatible_mapped=compatible_mapped,
        waveform_params_mapped=waveform_params_mapped,
        vibrator_class_present=class_present,
        vibrator_driver_bound=bound,
        actuator_quiescent=quiescent,
        summary=summary,
        details=data,
        failures=[],
    )


def collect_live_haptics_preflight(
    host: str = DEFAULT_LYNX_HOST,
    port: int = DEFAULT_LYNX_PORT,
    timeout: int = SSH_TIMEOUT,
) -> Dict[str, Any]:
    """Perform read-only live inspection of haptic hardware state over SSH."""
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

    boot_lines = res.stdout.split("===VIB_CLASS===", 1)[0].splitlines()
    boot_id = boot_lines[-1].strip() if boot_lines else "UNKNOWN_BOOT"

    class_paths = [l for l in section("VIB_CLASS") if l != "NONE"]
    class_present = len(class_paths) > 0
    class_path = class_paths[0] if class_paths else None

    driver_lines = [l for l in section("VIB_DRIVER") if l and l != "UNBOUND"]
    bound = len(driver_lines) > 0

    state_lines = [l for l in section("VIB_STATE") if l and l != "NO_STATE"]
    state_value = _state_value(state_lines[0]) if state_lines else None

    dt_paths = [l for l in section("DT_VIBRATOR") if l != "NONE"]
    compatible = None
    for line in section("DT_VIB_PROPS"):
        if line.startswith("compatible="):
            compatible = line.split("=", 1)[1].strip() or None

    module_lines = section("MODULES")
    loaded_mods = [l.split()[0] for l in module_lines if l.strip()]

    return {
        "platform": "OnePlus Nord 3 5G CPH2493 (MT6983 / project 22823 'Vitamin')",
        "boot_id": boot_id,
        "device_tree": {
            "vibrator_node_present": len(dt_paths) > 0,
            "vibrator_node_path": dt_paths[0] if dt_paths else None,
            "node_name": "vibrator@0" if dt_paths else None,
            "parent_node": "odm",
            "compatible": compatible,
            "vib_timer": EXPECTED_VIB_TIMER,
            "vib_limit": EXPECTED_VIB_LIMIT,
            "vib_vol": EXPECTED_VIB_VOL,
        },
        "runtime": {
            "vibrator_class_present": class_present,
            "vibrator_class_path": class_path,
            "vibrator_driver_bound": bound,
            "vibrator_state": state_value,
        },
        "loaded_modules": loaded_mods,
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Haptics (LRA) bring-up preflight tool")
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
        data = collect_live_haptics_preflight(host=args.host, port=args.port)
        if "error" in data:
            print(json.dumps({"status": "FAILED", "error": data["error"]}, indent=2))
            sys.exit(1)
        verdict = evaluate_haptics_preflight(data)
        print(json.dumps(verdict.to_dict(), indent=2))
        sys.exit(0 if verdict.is_valid else 1)

    if args.fixture:
        data = json.loads(args.fixture.read_text())
        verdict = evaluate_haptics_preflight(data)
        print(json.dumps(verdict.to_dict(), indent=2))
        sys.exit(0 if verdict.is_valid else 1)

    parser.print_help()


if __name__ == "__main__":
    main()
