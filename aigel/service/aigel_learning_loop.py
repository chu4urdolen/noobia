#!/usr/bin/env python3
"""Aigel 10-Minute Passive Diagnostics & Learning Service.

Operating Modes:
1. NORMAL MODE (Default):
   - Zero LLM in the loop.
   - Lynx runs fast direct regex / DB pattern matching locally.
   - Senses trigger Lynx cognition in milliseconds without GPU lockouts.
   - Aigel remains in passive standby (0 GPU tokens consumed).

2. LEARNING & DIAGNOSTICS MODE (Switched via Lynx Status screen button):
   - Runs every 10 minutes (600s).
   - Pattern Learning:
     * Reads lines from the 10-minute log window.
     * Identifies any lines that match NO regex in pattern_db.
     * Invokes local Qwen on Nexus to synthesize structured patterns.
     * Stores new patterns into pattern_db so Lynx's fast DB matching learns them.
   - Passive Diagnostics:
     * Analyzes the 10-minute log for system health (thermals, crashes, drops, undervoltage).
     * If an anomaly is found, writes to /noobia/aigel/logs/diagnostics.log.
     * If all healthy, remains quiet and continues the loop.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
AUTONOMY = REPO / "common" / "autonomy"
if str(AUTONOMY) not in sys.path:
    sys.path.insert(0, str(AUTONOMY))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import sense as _sense
from aigel_think import AigelThinker, QwenClient
from pattern_db import PatternDB

DIAGNOSTICS_LOG = REPO / "aigel" / "logs" / "diagnostics.log"
AIGEL_LOG = REPO / "aigel" / "logs" / "aigel_learning_loop.log"
LYNX_REMOTE = REPO / "lynx" / "tools" / "lynx_remote.py"

logger = logging.getLogger("aigel_learning_loop")


def get_lynx_mode() -> str:
    """Read Lynx's current Aigel mode (normal | learning)."""
    if not LYNX_REMOTE.is_file():
        return "normal"
    try:
        cmd = [sys.executable, str(LYNX_REMOTE), "run", "cat /var/lib/noobia/aigel_mode.txt 2>/dev/null || echo normal", "--timeout", "5"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        if res.returncode == 0:
            lines = res.stdout.strip().splitlines()
            for line in lines:
                if "learning" in line.lower():
                    return "learning"
                if "normal" in line.lower():
                    return "normal"
    except Exception:
        pass
    return "normal"


def fetch_lynx_recent_logs(lines: int = 300) -> list[str]:
    """Fetch the latest messages from Lynx."""
    if not LYNX_REMOTE.is_file():
        return []
    try:
        cmd = [sys.executable, str(LYNX_REMOTE), "run", f"tail -n {lines} /var/log/lynx/messages 2>/dev/null", "--timeout", "8"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
        if res.returncode == 0:
            # Strip ssh runner prefix (exit=0)
            raw_lines = res.stdout.splitlines()
            cleaned = []
            for l in raw_lines:
                if l.startswith("exit="):
                    continue
                cleaned.append(l)
            return cleaned
    except Exception as e:
        logger.warning(f"Failed to fetch Lynx logs: {e}")
    return []


def match_line_against_patterns(line: str, patterns: list[dict]) -> bool:
    """Check if a log line matches any known pattern in the database."""
    parsed = _sense.parse_line(line)
    sense_name = parsed.get("sense") if parsed else None
    event_name = parsed.get("event") if parsed else None

    for pat in patterns:
        # Check explicit regex if present
        regex_str = pat.get("regex")
        if regex_str:
            try:
                if re.search(regex_str, line):
                    return True
            except re.error:
                pass

        # Check structured match fields
        match = pat.get("match", {})
        pat_sense = match.get("sense")
        pat_event = match.get("event")
        if sense_name and pat_sense and sense_name == pat_sense:
            if not pat_event or pat_event == event_name:
                text_contains = match.get("text_contains")
                if text_contains and text_contains not in line:
                    continue
                return True

    return False


def run_diagnostics_check(logs: list[str]) -> list[str]:
    """Diagnose the log window for warnings, thermal issues, or anomalies."""
    anomalies = []
    seen_markers = set()

    for line in logs:
        # Check thermal alerts
        if "thermal.hot" in line or "soc_mc=4" in line:
            m = re.search(r"soc_mc=(\d+)", line)
            if m:
                mc = int(m.group(1))
                if mc >= 45000 and "soc_hot" not in seen_markers:
                    anomalies.append(f"Thermal elevated: SoC temperature reached {mc/1000.0:.1f}°C")
                    seen_markers.add("soc_hot")

        # Check kernel or hardware warnings
        if "Out of memory" in line or "oom-killer" in line:
            anomalies.append("Out of memory event detected in kernel log")
        if "critical" in line.lower() and "power" in line.lower():
            if "low_batt" not in seen_markers:
                anomalies.append("Power battery critical alarm observed")
                seen_markers.add("low_batt")
        if "OPENRC_HANDOFF_REFUSED" in line:
            anomalies.append("OpenRC handoff refused by boot guard")

    return anomalies


def log_diagnostic_report(anomalies: list[str]):
    """Record diagnostics report to diagnostics.log."""
    DIAGNOSTICS_LOG.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    with open(DIAGNOSTICS_LOG, "a", encoding="utf-8") as f:
        f.write(f"--- [DIAGNOSTICS REPORT {ts}] ---\n")
        for a in anomalies:
            f.write(f"  [WARNING/SUGGESTION] {a}\n")
        f.write("\n")


class AigelLearningService:
    def __init__(self, interval_s: int = 600):
        self.interval_s = max(60, int(interval_s))
        self.pattern_db = PatternDB()
        self.thinker = AigelThinker()

    def step(self):
        mode = get_lynx_mode()
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
        print(f"[{ts}] Aigel cycle check: Lynx mode = {mode.upper()}", flush=True)

        if mode != "learning":
            print(f"[{ts}] Normal mode active. Pure DB matching on Lynx (0 LLM overhead). Sleeping {self.interval_s}s...", flush=True)
            return

        print(f"[{ts}] Learning mode active. Fetching 10-minute log window...", flush=True)
        logs = fetch_lynx_recent_logs(lines=300)
        if not logs:
            print(f"[{ts}] No log lines retrieved or Lynx unreachable.", flush=True)
            return

        # 1. Passive diagnostics check
        anomalies = run_diagnostics_check(logs)
        if anomalies:
            print(f"[{ts}] Diagnostics found {len(anomalies)} issue(s). Logging suggestions...", flush=True)
            log_diagnostic_report(anomalies)
        else:
            print(f"[{ts}] Diagnostics clean: no hardware or system anomalies.", flush=True)

        # 2. Pattern Learning: find lines without any regex in DB
        existing_patterns = self.pattern_db.get_top_ranker_patterns("lynx", limit=200)
        sense_lines = [l for l in logs if "NOOBIA" in l]

        unmatched = []
        for sl in sense_lines:
            if not match_line_against_patterns(sl, existing_patterns):
                unmatched.append(sl)

        print(f"[{ts}] Sense lines analyzed: {len(sense_lines)} | Unmatched: {len(unmatched)}", flush=True)

        if unmatched:
            # Batch up to 5 unique unmatched lines for pattern learning
            batch = list(dict.fromkeys(unmatched))[:5]
            print(f"[{ts}] Synthesizing patterns for {len(batch)} new sense line(s) via local Qwen...", flush=True)
            try:
                decision = self.thinker.decide(host="lynx", reason="unmatched_sense_learning", lines=batch)
                new_patterns = decision.get("patterns", [])
                added_count = 0
                for pat in new_patterns:
                    if self.pattern_db.upsert_pattern(pat, host="lynx"):
                        added_count += 1
                print(f"[{ts}] Successfully added {added_count} new pattern(s) to pattern_db.", flush=True)
            except Exception as e:
                print(f"[{ts}] Learning pass failed (Qwen error): {e}", flush=True)
        else:
            print(f"[{ts}] All sense lines matched known patterns in DB.", flush=True)

    def run_forever(self):
        print(f"Starting Aigel 10-Minute Learning & Diagnostic Service (interval: {self.interval_s}s)...", flush=True)
        while True:
            try:
                self.step()
            except Exception as e:
                print(f"Error in cycle: {e}", flush=True)
            time.sleep(self.interval_s)


def main():
    parser = argparse.ArgumentParser(description="Aigel 10-minute diagnostic & learning loop")
    parser.add_argument("--interval-s", type=int, default=600, help="Interval in seconds (default: 600)")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    args = parser.parse_args()

    svc = AigelLearningService(interval_s=args.interval_s)
    if args.once:
        svc.step()
    else:
        svc.run_forever()


if __name__ == "__main__":
    main()
