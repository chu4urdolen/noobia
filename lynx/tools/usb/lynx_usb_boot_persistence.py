#!/usr/bin/env python3
"""Offline validator and evaluator for Lynx USB MTU3 ACM boot persistence.

Audits OpenRC service definitions, boot order constraints against Wi-Fi/SSH,
local disable switches, and graceful teardown mechanisms.
"""

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class UsbBootPersistenceVerdict:
    status: str  # "PERSISTENT_ENABLED", "PERSISTENT_DISABLED_SWITCH", "RUNTIME_ONLY", "UNCONFIGURED", "INVALID_ORDERING", "MALFORMED_SCRIPT"
    is_valid: bool
    is_persistent: bool
    disable_switch_active: bool
    service_in_runlevel: bool
    summary: str
    details: Dict[str, Any] = field(default_factory=dict)
    failures: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "is_valid": self.is_valid,
            "is_persistent": self.is_persistent,
            "disable_switch_active": self.disable_switch_active,
            "service_in_runlevel": self.service_in_runlevel,
            "summary": self.summary,
            "details": self.details,
            "failures": self.failures,
        }


def validate_init_script(script_text: str) -> Tuple[bool, List[str]]:
    """Validate OpenRC init script for safety invariants."""
    failures: List[str] = []

    if not script_text.startswith("#!/sbin/openrc-run"):
        failures.append("missing_or_invalid_openrc_shebang")

    # 1. Dependency checks
    depend_match = re.search(r"depend\s*\(\)\s*\{([^}]+)\}", script_text, re.DOTALL)
    if not depend_match:
        failures.append("missing_depend_block")
    else:
        dep_body = depend_match.group(1)
        # Check ordering: after bootmisc/modules
        if not re.search(r"after\s+.*\b(bootmisc|modules)\b", dep_body):
            failures.append("ordering_must_declare_after_bootmisc_or_modules")
        # Ordering REQUIREMENT: must declare after sshd so gadget can never delay sshd
        if not re.search(r"after\s+.*\bsshd\b", dep_body):
            failures.append("ordering_must_declare_after_sshd")
        # Ordering FORBIDDEN: must NOT declare before sshd
        if re.search(r"before\s+.*\bsshd\b", dep_body):
            failures.append("forbidden_ordering_before_sshd")
        # Must NOT depend on networking or wifi (must not block or couple)
        if re.search(r"need\s+.*\b(net|networking|lynx-wifi|wifi)\b", dep_body):
            failures.append("forbidden_need_dependency_on_networking")

    # 2. Local disable switch check
    if "/etc/lynx/disable-usb-gadget" not in script_text:
        failures.append("missing_local_disable_switch_check")

    # 3. Target UDC check
    if "11201000.usb0" not in script_text:
        failures.append("missing_target_udc_declaration")

    # 4. Teardown check (unbinding UDC)
    if not re.search(r"echo\s+['\"]{2}\s*>\s*['\"]?\$GADGET_DIR/UDC", script_text):
        failures.append("missing_udc_unbind_in_stop")

    # 5. Bounded timeout syntax check (BusyBox 1.37 positional syntax: timeout SECS PROG; reject -t)
    if re.search(r"timeout\s+-t\b", script_text):
        failures.append("forbidden_timeout_dash_t")
    elif not re.search(r"timeout\s+(-k\s+\d+\s+)?\d+\s+(modprobe|insmod|sh|mount)\b", script_text):
        failures.append("missing_positional_timeout_in_script")

    return len(failures) == 0, failures


def evaluate_boot_persistence(
    data: Optional[Dict[str, Any]],
    init_script_text: Optional[str] = None,
) -> UsbBootPersistenceVerdict:
    """Evaluate telemetry and service configuration state."""
    if not data:
        return UsbBootPersistenceVerdict(
            status="UNCONFIGURED",
            is_valid=False,
            is_persistent=False,
            disable_switch_active=False,
            service_in_runlevel=False,
            summary="Telemetry data missing or empty",
            failures=["missing_data"],
        )

    failures: List[str] = []
    details: Dict[str, Any] = {}

    runlevel_services = data.get("runlevel_default_services", [])
    service_in_runlevel = "lynx-usb-gadget" in runlevel_services
    disable_switch = data.get("disable_switch_present", False)
    udc_bound = data.get("udc_bound", False)
    ttygs_present = data.get("ttygs_present", False)
    mtu3_loaded = "mtu3" in data.get("modules", [])

    details["service_in_runlevel"] = service_in_runlevel
    details["disable_switch_present"] = disable_switch
    details["udc_bound"] = udc_bound
    details["ttygs_present"] = ttygs_present
    details["mtu3_loaded"] = mtu3_loaded

    # Script validation if provided or present in data
    script = init_script_text or data.get("init_script_content")
    if script:
        script_ok, script_failures = validate_init_script(script)
        details["script_failures"] = script_failures
        if not script_ok:
            failures.extend(script_failures)

    # Ordering failure from telemetry
    explicit_ordering_invalid = data.get("invalid_ordering_detected", False)
    if explicit_ordering_invalid:
        failures.append("invalid_runlevel_ordering_detected")

    if any("ordering" in f for f in failures):
        return UsbBootPersistenceVerdict(
            status="INVALID_ORDERING",
            is_valid=False,
            is_persistent=False,
            disable_switch_active=disable_switch,
            service_in_runlevel=service_in_runlevel,
            summary=f"USB service ordering violates safety policy: {', '.join(failures)}",
            details=details,
            failures=failures,
        )

    if failures:
        return UsbBootPersistenceVerdict(
            status="MALFORMED_SCRIPT",
            is_valid=False,
            is_persistent=False,
            disable_switch_active=disable_switch,
            service_in_runlevel=service_in_runlevel,
            summary=f"USB persistence configuration validation failed: {', '.join(failures)}",
            details=details,
            failures=failures,
        )

    if service_in_runlevel:
        if disable_switch:
            return UsbBootPersistenceVerdict(
                status="PERSISTENT_DISABLED_SWITCH",
                is_valid=True,
                is_persistent=True,
                disable_switch_active=True,
                service_in_runlevel=True,
                summary="USB gadget service installed in runlevel but inhibited by local disable switch",
                details=details,
                failures=[],
            )
        else:
            return UsbBootPersistenceVerdict(
                status="PERSISTENT_ENABLED",
                is_valid=True,
                is_persistent=True,
                disable_switch_active=False,
                service_in_runlevel=True,
                summary="USB gadget service persistent and active at boot",
                details=details,
                failures=[],
            )
    else:
        if mtu3_loaded or ttygs_present:
            return UsbBootPersistenceVerdict(
                status="RUNTIME_ONLY",
                is_valid=True,
                is_persistent=False,
                disable_switch_active=disable_switch,
                service_in_runlevel=False,
                summary="USB MTU3 gadget is active in runtime but not configured for cold-boot persistence",
                details=details,
                failures=[],
            )
        else:
            return UsbBootPersistenceVerdict(
                status="UNCONFIGURED",
                is_valid=True,
                is_persistent=False,
                disable_switch_active=disable_switch,
                service_in_runlevel=False,
                summary="USB MTU3 gadget is unconfigured and inactive at boot (quiescent baseline)",
                details=details,
                failures=[],
            )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Offline validator for Lynx USB MTU3 ACM boot persistence"
    )
    parser.add_argument(
        "fixture",
        type=Path,
        help="Path to boot persistence JSON fixture",
    )
    parser.add_argument(
        "--init-script",
        type=Path,
        default=None,
        help="Optional path to lynx-usb-gadget.initd script to audit",
    )
    args = parser.parse_args()

    if not args.fixture.exists():
        print(f"Error: file not found: {args.fixture}", file=sys.stderr)
        sys.exit(2)

    try:
        data = json.loads(args.fixture.read_text())
    except Exception as exc:
        print(f"Error: JSON parse failed: {exc}", file=sys.stderr)
        sys.exit(1)

    script_text = None
    if args.init_script and args.init_script.exists():
        script_text = args.init_script.read_text()

    verdict = evaluate_boot_persistence(data, init_script_text=script_text)
    print(json.dumps(verdict.to_dict(), indent=2))
    sys.exit(0 if verdict.is_valid else 1)


if __name__ == "__main__":
    main()
