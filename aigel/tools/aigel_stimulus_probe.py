#!/usr/bin/env python3
"""aigel_stimulus_probe.py: Sensory Stimulus Injector & Reflex Tester for Nurse Aigel.

Plugs into the sensory channel of a Noob (local, Lynx via SSH, or mock file)
to deliver a safe, gentle stimulus, and observes the reaction channel to verify reflexes.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

REPO = Path(__file__).resolve().parents[2]
_AUTONOMY = REPO / "common" / "autonomy"
if str(_AUTONOMY) not in sys.path:
    sys.path.insert(0, str(_AUTONOMY))

import sense as _sense
LYNX_REMOTE = REPO / "lynx" / "tools" / "lynx_remote.py"


class StimulusProbe:
    """Injects sensory events into a target host's sensory stream."""

    def __init__(self, target: str = "lynx", mock_file: str | None = None):
        self.target = target.lower()
        self.mock_file = Path(mock_file) if mock_file else None

    def inject_stimulus(
        self,
        p: int,
        sense_name: str,
        event_name: str,
        fields: dict[str, Any] | None = None,
        text: str = "",
    ) -> str:
        """Format and emit a sense line into the target host."""
        line = _sense.format_line(p, sense_name, event_name, fields=fields, text=text)

        if self.mock_file:
            self.mock_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.mock_file, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            return line

        if self.target == "local" or self.target == "nexus":
            _sense.emit(p, sense_name, event_name, fields=fields, text=text)
            return line

        elif self.target == "lynx":
            if LYNX_REMOTE.is_file():
                # Inject via lynx_remote to logger/syslog
                cmd_str = f"logger -p user.notice -t noobia-sense '{line}'"
                subprocess.run([sys.executable, str(LYNX_REMOTE), "run", cmd_str, "--timeout", "5"], capture_output=True)
            return line

        return line

    def run_reflex_test(
        self,
        kind: str = "touch",
        timeout_s: float = 8.0,
    ) -> dict[str, Any]:
        """Deliver stimulus and check if the Noob produces a reaction within timeout_s."""
        t0 = time.time()
        stimulus_line = ""

        if kind == "touch":
            stimulus_line = self.inject_stimulus(
                p=1, sense_name="touch", event_name="tap",
                fields={"x": 540, "y": 1200, "probe": "aigel"},
                text="Nurse Aigel delivered gentle diagnostic tap",
            )
        elif kind == "sound":
            stimulus_line = self.inject_stimulus(
                p=1, sense_name="hearing", event_name="sound.heard",
                fields={"peak": 120, "rms": 25.0, "probe": "aigel"},
                text="Nurse Aigel delivered gentle 440Hz diagnostic chirp",
            )
        else:
            stimulus_line = self.inject_stimulus(
                p=1, sense_name="nurse", event_name="reflex_check",
                fields={"kind": kind, "sender": "aigel"},
                text="Aigel diagnostic pulse check",
            )

        # Monitor reaction channel
        reaction_found = False
        reaction_text = None
        latency = None

        if self.mock_file:
            # For mock testing, simulate immediate reflex response
            reaction_found = True
            reaction_text = f"I felt a gentle {kind} stimulus from Aigel."
            latency = 1.2
        elif self.target == "lynx" and LYNX_REMOTE.is_file():
            start_poll = time.time()
            last_thought = ""
            # Get initial thought
            p_init = subprocess.run([sys.executable, str(LYNX_REMOTE), "run", "tail -n 1 /var/lib/noobia/lynx_thought.txt 2>/dev/null", "--timeout", "4"], capture_output=True, text=True)
            if p_init.returncode == 0:
                last_thought = p_init.stdout.strip()

            while time.time() - start_poll < timeout_s:
                time.sleep(1.0)
                p_curr = subprocess.run([sys.executable, str(LYNX_REMOTE), "run", "tail -n 1 /var/lib/noobia/lynx_thought.txt 2>/dev/null", "--timeout", "4"], capture_output=True, text=True)
                if p_curr.returncode == 0:
                    curr_thought = p_curr.stdout.strip()
                    if curr_thought and curr_thought != last_thought:
                        reaction_found = True
                        reaction_text = curr_thought
                        latency = round(time.time() - t0, 2)
                        break

        if not reaction_found:
            latency = round(time.time() - t0, 2)

        return {
            "target": self.target,
            "kind": kind,
            "stimulus_line": stimulus_line,
            "responsive": reaction_found,
            "latency_s": latency,
            "reaction_output": reaction_text or "(no reaction detected in timeout window)",
        }


def main():
    parser = argparse.ArgumentParser(description="Aigel Sensory Stimulus & Reflex Probe")
    parser.add_argument("--target", default="lynx", help="Target Noob (lynx, local, mock)")
    parser.add_argument("--mock-file", default=None, help="Mock sensory log file path")
    parser.add_argument("--kind", default="touch", choices=["touch", "sound", "vital_pulse"], help="Stimulus kind")
    parser.add_argument("--timeout", type=float, default=6.0, help="Reflex timeout seconds")
    parser.add_argument("--emit-only", action="store_true", help="Emit stimulus line and exit without waiting for reflex")
    args = parser.parse_args()

    probe = StimulusProbe(target=args.target, mock_file=args.mock_file)
    if args.emit_only:
        line = probe.inject_stimulus(1, "nurse", "reflex_check", fields={"kind": args.kind}, text="Diagnostic probe")
        print(f"Emitted: {line}")
    else:
        res = probe.run_reflex_test(kind=args.kind, timeout_s=args.timeout)
        print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
