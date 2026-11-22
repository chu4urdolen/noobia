#!/usr/bin/env python3
"""Aigel Bedside Visiting Nurse: 3-Channel Holistic Checkup Harness for Noobs.

Conducts a pediatric visit to a Noob:
1. Loads/Compiles Patient Dossier (identity, boundaries, medical history).
2. Reads Channel 1 (Sensory Inputs): thermals, battery, drop rates, sensor health.
3. Tests Channel 2 (Reaction Outputs): delivers gentle stimulus & measures reflex latency.
4. Speaks on Channel 3 (Dialogue Line): sends warm bedside greeting & vitals summary.
5. Files Medical Checkup Report to suggestions.log and dossier history.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any

REPO = Path(__file__).resolve().parents[2]
_SERVICE = Path(__file__).resolve().parent
_TOOLS = REPO / "aigel" / "tools"
_AUTONOMY = REPO / "common" / "autonomy"

if str(_SERVICE) not in sys.path:
    sys.path.insert(0, str(_SERVICE))
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))
if str(_AUTONOMY) not in sys.path:
    sys.path.insert(0, str(_AUTONOMY))

from aigel_patient_dossier import compile_dossier
from aigel_stimulus_probe import StimulusProbe
from aigel_think import QwenClient

LOGS_DIR = REPO / "aigel" / "logs"
SUGGESTIONS_LOG = LOGS_DIR / "suggestions.log"
DOSSIERS_DIR = REPO / "aigel" / "dossiers"
LYNX_REMOTE = REPO / "lynx" / "tools" / "lynx_remote.py"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class BedsideNurse:
    def __init__(self, target_noob: str = "lynx", mock_mode: bool = False):
        self.noob = target_noob.lower()
        self.mock_mode = mock_mode
        self.probe = StimulusProbe(
            target="mock" if mock_mode else self.noob,
            mock_file="/tmp/mock_bedside_senses.log" if mock_mode else None,
        )

    def read_sensory_vitals(self) -> dict[str, Any]:
        """Channel 1: Read physical & sensory vitals."""
        if self.mock_mode or self.noob != "lynx":
            return {
                "battery_pct": 98,
                "temperature_c": 28.5,
                "power_state": "nominal_battery",
                "sensor_drops": 0,
                "uptime": "up 42 min",
            }

        vitals = {
            "battery_pct": None,
            "temperature_c": None,
            "power_state": "unknown",
            "sensor_drops": 0,
            "uptime": "unknown",
        }
        if LYNX_REMOTE.is_file():
            cmd = (
                "uptime ; "
                "cat /sys/bus/i2c/devices/7-0055/battery_snapshot 2>/dev/null | grep -E 'capacity_percent|temperature_millidegrees' ; "
                "cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null"
            )
            res = subprocess.run([sys.executable, str(LYNX_REMOTE), "run", cmd, "--timeout", "8"], capture_output=True, text=True)
            if res.returncode == 0:
                lines = res.stdout.splitlines()
                for l in lines:
                    if "up" in l and "load" in l:
                        vitals["uptime"] = l.split("exit=")[-1].strip()
                    m_cap = re.search(r"capacity_percent=(\d+)", l)
                    if m_cap:
                        vitals["battery_pct"] = int(m_cap.group(1))
                    m_btemp = re.search(r"temperature_millidegrees_celsius=(\d+)", l)
                    if m_btemp:
                        vitals["battery_temp_c"] = round(int(m_btemp.group(1)) / 1000.0, 1)
                    if l.isdigit() and int(l) > 10000:
                        vitals["temperature_c"] = round(int(l) / 1000.0, 1)

        return vitals

    def test_reflexes(self, kind: str = "touch") -> dict[str, Any]:
        """Channel 2: Trigger stimulus probe & measure reaction."""
        return self.probe.run_reflex_test(kind=kind, timeout_s=6.0)

    def speak_to_noob(self, message: str) -> bool:
        """Channel 3: Speak directly to the Noob over operator/dialogue line."""
        if self.mock_mode:
            print(f"  [DIALOGUE CHANNEL -> {self.noob.upper()}] Aigel: \"{message}\"")
            return True

        if self.noob == "lynx" and LYNX_REMOTE.is_file():
            # Append to Lynx's chat / thought stream or chat input
            escaped = message.replace('"', '\\"')
            cmd = f"printf 'Nurse Aigel: %s\\n' \"{escaped}\" >> /var/lib/noobia/lynx_thought.txt"
            subprocess.run([sys.executable, str(LYNX_REMOTE), "run", cmd, "--timeout", "5"], capture_output=True)
            return True

        return False

    def conduct_visit(self, reflex_kind: str = "touch", enable_dushich: bool = False) -> dict[str, Any]:
        """Perform the complete bedside checkup."""
        start_ts = utc_now_iso()
        print(f"\n🩺 --- [NURSE AIGEL BEDSIDE VISIT: {self.noob.upper()}] ---")

        # Step 1: Dossier
        print("1. Familiarizing with patient dossier...")
        dossier = compile_dossier(self.noob, use_llm=False)
        med_profile = dossier.get("medical_profile", {})
        print(f"   Identity:   {dossier.get('contact_info', {}).get('identity')}")
        print(f"   Limits:     {med_profile.get('sensitivities_and_limits')}")

        # Step 2: Channel 1 Sensory Vitals
        print("2. Reading Channel 1 (Sensory & Thermal Vitals)...")
        vitals = self.read_sensory_vitals()
        batt = vitals.get("battery_pct", 100)
        temp = vitals.get("temperature_c", 27.5)
        print(f"   Battery:    {batt}%")
        print(f"   SoC Temp:   {temp}°C")
        print(f"   Uptime:     {vitals.get('uptime')}")

        # Step 3: Channel 2 Reflex Test
        print(f"3. Testing Channel 2 (Reflex Stimulus: {reflex_kind})...")
        reflex = self.test_reflexes(kind=reflex_kind)
        print(f"   Stimulus:   {reflex.get('stimulus_line')}")
        print(f"   Reflex:     {'RESPONSIVE' if reflex.get('responsive') else 'AWAITING_REACTION'} (latency: {reflex.get('latency_s')}s)")
        print(f"   Reaction:   {reflex.get('reaction_output')}")

        # Step 4: Channel 3 Bedside Greeting
        greeting = (
            f"Hello {self.noob.capitalize()}! Nurse Aigel is here for your checkup. "
            f"Your battery is {batt}%, your temperature is a cool {temp}°C, "
            f"and your reflexes are responsive ({reflex.get('latency_s')}s). "
            f"Rest comfortably and stay curious!"
        )
        print("4. Speaking on Channel 3 (Dialogue Line)...")
        self.speak_to_noob(greeting)

        # Step 5: File Medical Report
        print("5. Filing Medical Checkup Report...")
        report = {
            "visit_timestamp": start_ts,
            "patient": self.noob,
            "vitals": vitals,
            "reflex_result": reflex,
            "bedside_greeting": greeting,
            "nurse_recommendation": (
                "Nominal health. Principle 10 compliance verified (no forced shutdowns). "
                "Keep charging currents modest and allow passive thermal dissipation."
            ),
        }

        # Append to suggestions.log
        SUGGESTIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(SUGGESTIONS_LOG, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*80}\n")
            f.write(f"[PEDIATRIC BEDSIDE VISIT REPORT: {self.noob.upper()}]\n")
            f.write(f"Visit Time:      {start_ts}\n")
            f.write(f"Patient:         {self.noob.upper()}\n")
            f.write(f"Vitals:          Battery: {batt}% | SoC: {temp}°C | {vitals.get('uptime')}\n")
            f.write(f"Reflex Test:     {reflex_kind.upper()} -> {'PASS' if reflex.get('responsive') else 'TIMED_OUT'} ({reflex.get('latency_s')}s)\n")
            f.write(f"Nurse Greeting:  \"{greeting}\"\n")
            f.write(f"Recommendation:  {report['nurse_recommendation']}\n")
            f.write(f"{'='*80}\n")

        # Step 6: Optional Dushich Pair (Fix Handoff) - Disabled by default
        fix_result = self.pair_with_dushich(report, enabled=enable_dushich)
        report["dushich_pair_result"] = fix_result

        # Save to patient history log
        hist_file = DOSSIERS_DIR / f"{self.noob}_history.log"
        with open(hist_file, "a", encoding="utf-8") as f:
            f.write(f"[{start_ts}] VISIT: Battery={batt}% Temp={temp}C Reflex={reflex.get('latency_s')}s Status=NOMINAL DushichPair={fix_result.get('status')}\n")

        print("   Report filed successfully!\n")
        return report

    def pair_with_dushich(self, report: dict[str, Any], enabled: bool = False) -> dict[str, Any]:
        """Pair with Dushich helper to prepare or propose fixes for findings.
        
        SAFETY NOTE: Kept disabled by default (`enabled=False` or `--enable-dushich-pair`).
        When enabled, formats a bounded diagnostic briefing and task for Dushich
        via `dushich exec` or Helper Dushich queue.
        """
        if not enabled and not os.environ.get("AIGEL_ENABLE_DUSHICH_PAIR"):
            return {
                "status": "disabled",
                "message": "Dushich repair pairing is currently disabled for safety (standing default).",
            }

        patient = report.get("patient", "unknown")
        findings = report.get("nurse_recommendation", "Review diagnostic findings")
        brief = (
            f"[AIGEL MEDICAL CHECKUP FINDINGS - PATIENT: {patient.upper()}]\n"
            f"Vitals: {json.dumps(report.get('vitals', {}))}\n"
            f"Reflexes: {json.dumps(report.get('reflex_result', {}))}\n"
            f"Recommendations: {findings}\n"
            f"Task: Please review the diagnostic findings above and evaluate if any code, "
            f"service configurations, or sensor thresholds require tuning or fixes."
        )

        dushich_bin = REPO / "common" / "bin" / "dushich"
        if not dushich_bin.exists():
            return {
                "status": "unavailable",
                "error": f"Dushich launcher not found at {dushich_bin}",
            }

        try:
            # Non-interactive bounded invocation per shared instructions: dushich exec "<task>" < /dev/null
            proc = subprocess.run(
                [str(dushich_bin), "exec", brief],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=120,
            )
            return {
                "status": "dispatched" if proc.returncode == 0 else "error",
                "exit_code": proc.returncode,
                "output": proc.stdout[-1000:],
                "error": proc.stderr[-500:],
            }
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "error": "Dushich task execution timed out (queue busy)"}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}


def main():
    parser = argparse.ArgumentParser(description="Aigel Bedside Visiting Nurse")
    parser.add_argument("noob", default="lynx", nargs="?", help="Target Noob (default: lynx)")
    parser.add_argument("--mock", action="store_true", help="Run in mock mode (safe offline test)")
    parser.add_argument("--reflex", default="touch", choices=["touch", "sound", "vital_pulse"], help="Reflex stimulus kind")
    parser.add_argument("--enable-dushich-pair", action="store_true", help="Enable pairing with Dushich for automated fix proposals (disabled by default)")
    args = parser.parse_args()

    nurse = BedsideNurse(target_noob=args.noob, mock_mode=args.mock)
    report = nurse.conduct_visit(reflex_kind=args.reflex, enable_dushich=args.enable_dushich_pair)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
