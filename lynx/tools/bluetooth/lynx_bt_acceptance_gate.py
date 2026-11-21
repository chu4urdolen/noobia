#!/usr/bin/env python3
"""Offline checker for Lynx Bluetooth cold-boot or sustained-hold acceptance trials.

Validates that a Bluetooth trial receipt contains:
1. Fresh, non-stale boot ID.
2. Unbroken sequence of healthy system samples across the trial hold.
3. Verified radio power-off at teardown (hci0 disappeared, service stopped).
4. Bounded recovery record (no partition/runlevel writes, watchdog safely canceled).
"""

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional

UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


@dataclass
class BluetoothTrialVerdict:
    status: str  # "PASS", "STALE_EVIDENCE", "ABSENT_EVIDENCE", "FAILED"
    is_valid: bool
    summary: str
    boot_id: Optional[str] = None
    samples_evaluated: int = 0
    checks_passed: List[str] = field(default_factory=list)
    failures: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "is_valid": self.is_valid,
            "summary": self.summary,
            "boot_id": self.boot_id,
            "samples_evaluated": self.samples_evaluated,
            "checks_passed": self.checks_passed,
            "failures": self.failures,
        }


def evaluate_bluetooth_trial(
    receipt_data: Optional[Dict[str, Any]],
    reference_boot_id: Optional[str] = None,
) -> BluetoothTrialVerdict:
    """Evaluate an offline trial receipt against cold-boot / sustained acceptance criteria."""
    if not receipt_data:
        return BluetoothTrialVerdict(
            status="ABSENT_EVIDENCE",
            is_valid=False,
            summary="Receipt data is missing or empty",
            failures=["missing_receipt_data"],
        )

    failures: List[str] = []
    checks_passed: List[str] = []

    # 1. Fresh Boot ID Gate
    boot_id = receipt_data.get("boot_id")
    if not boot_id or not isinstance(boot_id, str):
        failures.append("missing_or_invalid_boot_id")
    elif not UUID_PATTERN.match(boot_id):
        failures.append(f"malformed_boot_id_format: {boot_id}")
    elif reference_boot_id and boot_id.strip() == reference_boot_id.strip():
        failures.append(f"stale_boot_id_matches_reference: {boot_id}")
    else:
        checks_passed.append("fresh_boot_id_verified")

    # 2. Safety Bounds & Recovery Record Gate
    partition_writes = receipt_data.get("partition_writes")
    if partition_writes is True:
        failures.append("forbidden_partition_writes_detected")
    elif partition_writes is False:
        checks_passed.append("zero_partition_writes_confirmed")
    else:
        failures.append("missing_partition_writes_safety_record")

    runlevel_writes = receipt_data.get("runlevel_writes")
    if runlevel_writes is True:
        failures.append("forbidden_runlevel_writes_detected")
    elif runlevel_writes is False:
        checks_passed.append("zero_runlevel_writes_confirmed")
    else:
        failures.append("missing_runlevel_writes_safety_record")

    if receipt_data.get("watchdog_remains_armed") is True:
        failures.append("watchdog_remains_armed")
    elif "watchdog_error" in receipt_data and receipt_data["watchdog_error"]:
        failures.append(f"watchdog_cancellation_error: {receipt_data['watchdog_error']}")
    else:
        checks_passed.append("watchdog_safely_disarmed")

    # 3. Radio Start & Power-Off at End Gate
    radio_started = receipt_data.get("radio_started")
    if radio_started is not True:
        failures.append("radio_was_never_started_in_trial")
    else:
        checks_passed.append("radio_started_verified")

    state = receipt_data.get("state")
    if state == "stopped-after-healthy-trial":
        checks_passed.append("radio_powered_off_cleanly")
    elif state == "running-after-healthy-trial":
        failures.append("radio_not_powered_off_at_trial_end")
    elif state == "failed":
        failures.append(f"trial_state_marked_failed: {receipt_data.get('error', 'unknown error')}")
    else:
        failures.append(f"unrecognized_or_incomplete_trial_state: {state}")

    if "stop_error" in receipt_data and receipt_data["stop_error"]:
        failures.append(f"radio_teardown_error: {receipt_data['stop_error']}")

    # Check teardown step execution if steps list exists
    steps = receipt_data.get("steps", [])
    step_exits = {s.get("name"): s.get("exit") for s in steps if isinstance(s, dict)}
    if "stopped_check" in step_exits:
        if step_exits["stopped_check"] != 0:
            failures.append(f"stopped_check_failed_exit_{step_exits['stopped_check']}")
        else:
            checks_passed.append("stopped_check_step_passed")

    # 4. Sustained Health Samples Gate
    health_samples = receipt_data.get("health_samples", [])
    if not health_samples:
        failures.append("no_health_samples_recorded_during_hold")
    else:
        sample_errors = []
        for idx, sample in enumerate(health_samples):
            if not isinstance(sample, dict):
                sample_errors.append(f"sample_{idx}_not_dict")
                continue
            sample_boot = sample.get("boot_id")
            if sample_boot != boot_id:
                sample_errors.append(f"sample_{idx}_boot_id_mismatch_{sample_boot}_vs_{boot_id}")
            issues = sample.get("issues", [])
            if issues:
                sample_errors.append(f"sample_{idx}_reported_issues: {issues}")
            battery = sample.get("battery", {})
            cap = battery.get("capacity_percent", 0)
            if cap < 15:
                sample_errors.append(f"sample_{idx}_battery_below_15_percent: {cap}%")
            thermal = sample.get("thermal", {})
            max_mc = thermal.get("max_mC", 0)
            if max_mc >= 55000:
                sample_errors.append(f"sample_{idx}_thermal_trip_exceeded_55C: {max_mc}mC")

        if sample_errors:
            failures.extend(sample_errors)
        else:
            checks_passed.append(f"all_{len(health_samples)}_health_samples_healthy")

    # Final Verdict Classification
    samples_count = len(health_samples)
    if not failures:
        return BluetoothTrialVerdict(
            status="PASS",
            is_valid=True,
            summary=f"Bluetooth trial passed all gates ({samples_count} healthy samples, clean teardown)",
            boot_id=boot_id,
            samples_evaluated=samples_count,
            checks_passed=checks_passed,
            failures=[],
        )
    elif any("stale_boot_id" in f for f in failures):
        return BluetoothTrialVerdict(
            status="STALE_EVIDENCE",
            is_valid=False,
            summary="Trial receipt contains stale boot ID matching reference pre-boot ID",
            boot_id=boot_id,
            samples_evaluated=samples_count,
            checks_passed=checks_passed,
            failures=failures,
        )
    else:
        return BluetoothTrialVerdict(
            status="FAILED",
            is_valid=False,
            summary=f"Bluetooth trial failed validation ({len(failures)} issue(s))",
            boot_id=boot_id,
            samples_evaluated=samples_count,
            checks_passed=checks_passed,
            failures=failures,
        )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Offline validator for Lynx Bluetooth cold-boot / sustained acceptance trials"
    )
    parser.add_argument("receipt_file", type=Path, help="Path to trial result.json")
    parser.add_argument(
        "--reference-boot-id",
        type=str,
        default=None,
        help="Prior boot ID before trial cold-boot to ensure freshness",
    )
    args = parser.parse_args()

    if not args.receipt_file.exists():
        print(
            json.dumps(
                BluetoothTrialVerdict(
                    status="ABSENT_EVIDENCE",
                    is_valid=False,
                    summary=f"File not found: {args.receipt_file}",
                    failures=["file_not_found"],
                ).to_dict(),
                indent=2,
            )
        )
        sys.exit(2)

    try:
        data = json.loads(args.receipt_file.read_text())
    except Exception as exc:
        print(
            json.dumps(
                BluetoothTrialVerdict(
                    status="FAILED",
                    is_valid=False,
                    summary=f"Failed to parse JSON: {exc}",
                    failures=["json_parse_error"],
                ).to_dict(),
                indent=2,
            )
        )
        sys.exit(1)

    verdict = evaluate_bluetooth_trial(data, reference_boot_id=args.reference_boot_id)
    print(json.dumps(verdict.to_dict(), indent=2))
    sys.exit(0 if verdict.is_valid else 1)


if __name__ == "__main__":
    main()
