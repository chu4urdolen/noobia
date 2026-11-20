"""Offline preflight gate for the Lynx USB mtu3 driver trial.

This tool ONLY evaluates. It never loads a module, writes sysfs, or touches
hardware. It reports a JSON ``ready`` / ``blocked`` decision from a set of
observations about Lynx's current state, using pins taken from
``lynx/linux-port/docs/CURRENT-HANDOFF.md`` (2026-11-20):

* exact V53 boot id ``0fe847d2-44d6-4ac1-9000-2c99df1a51d8``
* stock ``mtu3.ko`` SHA-256 ``d3c59fa794a6e02f014dd0de660592bb66c9d7f8eb941c1d1183f8a3322bb467``
* controller ``11201000.usb0`` present but with no bound ``mtu3`` driver
* only ``dummy_udc.0`` registered under ``/sys/class/udc``

The core decision is the pure function :func:`evaluate_preflight`, which takes
a plain dict of observations and returns a JSON-serializable report. That
keeps the guard fully testable offline with fixtures.

Live mode (``--live --allow-live``) is an opt-in convenience that fills the
observation dict through bounded, read-only, pinned SSH reads. It is refused
unless the caller passes ``--allow-live`` explicitly, so ordinary runs and
tests can never contact the phone by accident.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time
from typing import Any, Mapping, Sequence

# --- Pins from CURRENT-HANDOFF.md (2026-11-20) ------------------------------

#: Exact V53 Alpine boot the gate must run on (handoff "Current foothold").
PINNED_V53_BOOT_ID = "0fe847d2-44d6-4ac1-9000-2c99df1a51d8"

#: SHA-256 of the exact stock mtu3.ko (handoff "Hardware still to finish").
PINNED_MTU3_SHA256 = (
    "d3c59fa794a6e02f014dd0de660592bb66c9d7f8eb941c1d1183f8a3322bb467"
)

#: USB gadget controller on the MT6983 (handoff: present, unbound).
CONTROLLER_NAME = "11201000.usb0"

#: Gate: fresh >=50% charge before any RAM-only driver trial.
MIN_BATTERY_PERCENT = 50

#: UDC names that are allowed while the gate checks "only dummy UDC".
DUMMY_UDC_PREFIX = "dummy_udc."

#: Default pinned SSH target: Lynx Alpine, port 2222 (handoff foothold).
DEFAULT_LYNX_HOST = "192.168.100.107"
DEFAULT_LYNX_SSH_PORT = 2222

#: Pinned credentials and hosts for Lynx
ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_LYNX_KEY = ROOT_DIR / "secrets/nexus_lynx_ed25519"
DEFAULT_LYNX_KNOWN_HOSTS = ROOT_DIR / "secrets/lynx_known_hosts"

#: Nexus location of the matching stock mtu3.ko from the August OTA
DEFAULT_STOCK_MTU3_PATH = (
    ROOT_DIR
    / "linux-port/artifacts/stock-cph2493-August-eu-ota/vendor-ramdisk-unpacked/lib/modules/mtu3.ko"
)

# --- Exit codes --------------------------------------------------------------

EXIT_READY = 0
EXIT_ERROR = 1
EXIT_BLOCKED = 3
EXIT_LIVE_REFUSED = 4

REQUIRED_KEYS = frozenset({
    "boot_id",
    "kernel_release",
    "mtu3_sha256",
    "module_vermagic",
    "battery_percent",
    "charging",
    "safe_power",
    "health_clear",
    "controller_present",
    "controller_bound_driver",
    "udc_devices",
})


class PreflightInputError(ValueError):
    """An observation dict is missing keys or has unusable types."""


def _clean(value: Any) -> str:
    if not isinstance(value, str):
        raise PreflightInputError("string expected, got %r" % type(value).__name__)
    return value.strip()


def _num(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PreflightInputError("number expected, got %r" % type(value).__name__)
    return float(value)


def _flag(value: Any) -> bool:
    if not isinstance(value, bool):
        raise PreflightInputError("boolean expected, got %r" % type(value).__name__)
    return value


def _check_boot_id(obs: Mapping[str, Any]) -> tuple[bool, str]:
    got = _clean(obs["boot_id"]).lower()
    if got == PINNED_V53_BOOT_ID:
        return True, "boot id matches pinned V53 boot"
    return False, "boot id %r != pinned %s" % (got, PINNED_V53_BOOT_ID)


def _check_mtu3_sha(obs: Mapping[str, Any]) -> tuple[bool, str]:
    got = _clean(obs["mtu3_sha256"]).lower()
    if len(got) != 64:
        return False, "mtu3 SHA is not 64 hex chars"
    if got == PINNED_MTU3_SHA256:
        return True, "mtu3.ko SHA matches the exact stock module"
    return False, "mtu3 SHA %r != pinned %s" % (got, PINNED_MTU3_SHA256)


def _check_vermagic(obs: Mapping[str, Any]) -> tuple[bool, str]:
    release = _clean(obs["kernel_release"])
    vermagic = _clean(obs["module_vermagic"])
    module_release = vermagic.split()[0] if vermagic.split() else ""
    if module_release == release:
        return True, "module vermagic release %r matches kernel %r" % (release, release)
    return False, "module vermagic %r does not match kernel %r" % (vermagic, release)


def _check_battery(obs: Mapping[str, Any]) -> tuple[bool, str]:
    percent = _num(obs["battery_percent"])
    if not 0.0 <= percent <= 100.0:
        return False, "battery percent out of range: %s" % percent
    if percent >= MIN_BATTERY_PERCENT:
        return True, "battery %g%% >= %g%%" % (percent, MIN_BATTERY_PERCENT)
    return False, "battery %g%% below %g%% gate" % (percent, MIN_BATTERY_PERCENT)


def _check_power(obs: Mapping[str, Any]) -> tuple[bool, str]:
    if _flag(obs["charging"]):
        return True, "charging"
    if _flag(obs["safe_power"]):
        return True, "not charging but on a safe power source"
    return False, "discharging on no safe power source"


def _check_health(obs: Mapping[str, Any]) -> tuple[bool, str]:
    if _flag(obs["health_clear"]):
        return True, "health clear"
    return False, "health issues present"


def _check_controller(obs: Mapping[str, Any]) -> tuple[bool, str]:
    if not _flag(obs["controller_present"]):
        return False, "controller %s missing" % CONTROLLER_NAME
    bound = obs["controller_bound_driver"]
    if bound is None or (isinstance(bound, str) and not bound.strip()):
        return True, "controller %s present and unbound" % CONTROLLER_NAME
    return False, "controller %s has driver bound: %r" % (CONTROLLER_NAME, bound)


def _check_udc(obs: Mapping[str, Any]) -> tuple[bool, str]:
    devices = obs["udc_devices"]
    if not isinstance(devices, (list, tuple)) or not all(isinstance(d, str) for d in devices):
        raise PreflightInputError("udc_devices must be a list of strings")
    if not devices:
        return False, "no UDC registered; expected dummy_udc.0"
    if all(d.startswith(DUMMY_UDC_PREFIX) for d in devices):
        return True, "only dummy UDC(s) registered: %s" % ", ".join(devices)
    bad = [d for d in devices if not d.startswith(DUMMY_UDC_PREFIX)]
    return False, "non-dummy UDC(s) registered: %s" % ", ".join(bad)


def evaluate_preflight(observations: Mapping[str, Any]) -> dict[str, Any]:
    """Pure offline guard: turn observations into a ready/blocked report.

    No I/O, no clock, no network. Raises :class:`PreflightInputError` when a
    required key is missing or mistyped, so callers fail loudly rather than
    guessing about phone state.
    """
    missing = sorted(REQUIRED_KEYS - set(observations))
    if missing:
        raise PreflightInputError("missing observation keys: %s" % ", ".join(missing))

    checks = {
        "boot_id": _check_boot_id(observations),
        "mtu3_sha": _check_mtu3_sha(observations),
        "vermagic": _check_vermagic(observations),
        "battery": _check_battery(observations),
        "power": _check_power(observations),
        "health": _check_health(observations),
        "controller_unbound": _check_controller(observations),
        "dummy_udc_only": _check_udc(observations),
    }
    blockers = [name for name, (passed, _detail) in checks.items() if not passed]
    report = {
        "state": "ready" if not blockers else "blocked",
        "ready": not blockers,
        "blockers": blockers,
        "checks": {
            name: {"pass": passed, "detail": detail} for name, (passed, detail) in checks.items()
        },
        "pins": {
            "v53_boot_id": PINNED_V53_BOOT_ID,
            "mtu3_sha256": PINNED_MTU3_SHA256,
            "controller": CONTROLLER_NAME,
            "min_battery_percent": MIN_BATTERY_PERCENT,
            "allowed_udc_prefix": DUMMY_UDC_PREFIX,
        },
        "side_effects": "none: read-only preflight, no module load, no sysfs write",
    }
    return report


# --- Offline fixture path ----------------------------------------------------

def load_fixture(path: str | Path) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        raise PreflightInputError("cannot read fixture %s: %s" % (path, exc)) from exc
    if not isinstance(data, dict):
        raise PreflightInputError("fixture must be a JSON object")
    return data


def build_ssh_command(
    host: str,
    port: int,
    script: str,
    key_path: Path | None = None,
    known_hosts: Path | None = None,
    connect_timeout: int = 5,
    command_timeout: int = 20,
) -> list[str]:
    """Construct a bounded, pinned SSH command line with strict security settings."""
    cmd = [
        "ssh",
        "-o", f"ConnectTimeout={connect_timeout}",
        "-o", "BatchMode=yes",
        "-o", "IdentitiesOnly=yes",
        "-o", "IdentityAgent=none",
        "-o", "StrictHostKeyChecking=yes",
        "-o", "GlobalKnownHostsFile=/dev/null",
        "-o", "HostKeyAlias=lynx",
    ]
    if known_hosts and known_hosts.exists():
        cmd.extend(["-o", f"UserKnownHostsFile={known_hosts}"])
    if key_path and key_path.exists():
        cmd.extend(["-i", str(key_path)])

    cmd.extend([
        "-p", str(port),
        f"root@{host}",
        f"timeout {command_timeout} sh -c {shlex.quote(script)}",
    ])
    return cmd


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline Lynx USB mtu3 preflight gate (read-only; makes no phone changes).",
    )
    parser.add_argument("--fixture", help="JSON file with observation values (offline mode).")
    parser.add_argument("--live", action="store_true",
                        help="collect observations via bounded pinned SSH reads (read-only).")
    parser.add_argument("--allow-live", action="store_true",
                        help="actually permit --live to contact Lynx; refused without it.")
    parser.add_argument("--host", default=DEFAULT_LYNX_HOST, help="pinned Lynx SSH host.")
    parser.add_argument("--port", type=int, default=DEFAULT_LYNX_SSH_PORT, help="pinned SSH port.")
    parser.add_argument("--stock-module", default=str(DEFAULT_STOCK_MTU3_PATH),
                        help="path on Nexus to stock mtu3.ko for SHA/vermagic check.")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="print the JSON report to stdout.")
    args = parser.parse_args(argv)

    if args.live and not args.allow_live:
        sys.stderr.write(
            "refused: --live would contact Lynx; rerun with --live --allow-live "
            "to confirm an attended, read-only session\n"
        )
        return EXIT_LIVE_REFUSED

    if args.live:
        try:
            observations = collect_live(args.host, args.port, Path(args.stock_module))
        except LiveCollectionError as exc:
            sys.stderr.write("live collection failed: %s\n" % exc)
            return EXIT_ERROR
    else:
        if not args.fixture:
            parser.error("provide --fixture PATH (offline) or --live --allow-live")
            return EXIT_ERROR  # unreachable; parser.error exits 2
        try:
            observations = load_fixture(args.fixture)
        except PreflightInputError as exc:
            sys.stderr.write("fixture error: %s\n" % exc)
            return EXIT_ERROR

    try:
        report = evaluate_preflight(observations)
    except PreflightInputError as exc:
        sys.stderr.write("invalid observations: %s\n" % exc)
        return EXIT_ERROR

    if args.as_json:
        print(json.dumps(report, indent=2))
    else:
        print("state=%s" % report["state"])
        for name, (passed, detail) in report["checks"].items():
            print("  [%s] %s: %s" % ("ok" if passed else "XX", name, detail))
        if report["blockers"]:
            print("blockers: %s" % ", ".join(report["blockers"]))

    return EXIT_READY if report["ready"] else EXIT_BLOCKED


# --- Live (read-only) collection, opt-in -------------------------------------

class LiveCollectionError(RuntimeError):
    """A bounded SSH read failed or returned unusable data."""


#: Strictly read-only remote commands to inspect actual Alpine layout.
def _live_script(ctl: str = CONTROLLER_NAME) -> str:
    return (
        "echo ===LYNX_STATUS===; "
        "/usr/local/bin/lynx-status --assert-ready 2>/dev/null || true; "
        "echo ===SYSFS===; "
        "echo KERNEL=$(uname -r); "
        "test -d /sys/bus/platform/devices/{ctl} && echo CTL_PRESENT=1 || echo CTL_PRESENT=0; "
        "test -e /sys/bus/platform/devices/{ctl}/driver && echo BOUND=$(readlink -f /sys/bus/platform/devices/{ctl}/driver) || echo BOUND=; "
        "echo UDCS=$(ls /sys/class/udc 2>/dev/null | tr '\\n' ',')"
    ).format(ctl=ctl)


def parse_live_output(
    remote_stdout: str,
    stock_module_path: Path | str,
) -> dict[str, Any]:
    """Parse remote Lynx Alpine probe output and combine with verified stock module data."""
    stock_module_path = Path(stock_module_path)
    if not stock_module_path.is_file():
        raise LiveCollectionError("stock mtu3.ko not found at %s" % stock_module_path)

    try:
        data = stock_module_path.read_bytes()
        mtu3_sha = hashlib.sha256(data).hexdigest()
    except OSError as exc:
        raise LiveCollectionError("cannot read stock mtu3.ko: %s" % exc) from exc

    try:
        proc = subprocess.run(
            ["modinfo", "-F", "vermagic", str(stock_module_path)],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        module_vermagic = proc.stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise LiveCollectionError("modinfo failed on %s: %s" % (stock_module_path, exc)) from exc

    status_json_text = ""
    sysfs_lines: list[str] = []
    in_status = False
    in_sysfs = False

    for line in remote_stdout.splitlines():
        if "===LYNX_STATUS===" in line:
            in_status = True
            in_sysfs = False
            continue
        if "===SYSFS===" in line:
            in_status = False
            in_sysfs = True
            continue
        if in_status:
            status_json_text += line + "\n"
        elif in_sysfs:
            sysfs_lines.append(line)

    status_data: dict[str, Any] = {}
    if status_json_text.strip():
        try:
            status_data = json.loads(status_json_text.strip())
        except ValueError as exc:
            raise LiveCollectionError("lynx-status returned invalid JSON: %s" % exc) from exc

    values: dict[str, str] = {}
    for line in sysfs_lines:
        k, _, v = line.partition("=")
        values[k.strip()] = v.strip()

    boot_id = status_data.get("boot_id") or values.get("BOOT_ID", "")
    if not boot_id:
        raise LiveCollectionError("boot_id missing from phone output")

    kernel = values.get("KERNEL", "")
    if not kernel:
        raise LiveCollectionError("kernel release missing from phone output")

    ctl_present = values.get("CTL_PRESENT", "0") == "1"
    bound = values.get("BOUND", "")
    udc_csv = values.get("UDCS", "")
    udc_devices = [d.strip() for d in udc_csv.split(",") if d.strip()]

    battery_info = status_data.get("battery", {})
    if "capacity_percent" in battery_info:
        battery_percent = float(battery_info["capacity_percent"])
        current_mA = int(battery_info.get("current_mA_signed", 0))
        charging = current_mA > 0
        safe_power = current_mA >= 0 or battery_percent >= 100.0
    else:
        raise LiveCollectionError("battery status missing from lynx-status")

    issues = status_data.get("issues", [])
    health_clear = len(issues) == 0

    return {
        "boot_id": boot_id,
        "kernel_release": kernel,
        "mtu3_sha256": mtu3_sha,
        "module_vermagic": module_vermagic,
        "battery_percent": battery_percent,
        "charging": charging,
        "safe_power": safe_power,
        "health_clear": health_clear,
        "controller_present": ctl_present,
        "controller_bound_driver": bound,
        "udc_devices": udc_devices,
    }


def collect_live(
    host: str,
    port: int,
    stock_module_path: Path = DEFAULT_STOCK_MTU3_PATH,
    key_path: Path | None = DEFAULT_LYNX_KEY,
    known_hosts: Path | None = DEFAULT_LYNX_KNOWN_HOSTS,
    timeout: int = 40,
) -> dict[str, Any]:
    """Bounded pinned read-only SSH reads; never writes or loads anything."""
    script = _live_script(CONTROLLER_NAME)
    cmd = build_ssh_command(
        host=host,
        port=port,
        script=script,
        key_path=key_path,
        known_hosts=known_hosts,
        connect_timeout=5,
        command_timeout=20,
    )
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        raise LiveCollectionError("ssh read failed: %s" % exc) from exc
    if proc.returncode != 0:
        raise LiveCollectionError("ssh read exited %s: %s" % (proc.returncode, proc.stderr.strip()[:300]))

    return parse_live_output(proc.stdout, stock_module_path)


if __name__ == "__main__":
    sys.exit(main())
