#!/usr/bin/env python3
"""Aigel Sensory Perception & Diagnostic Engine.

Observes a Noob's sensory and system logs.
1. When a log line matches NO regex in the pattern DB:
   - Analyzes what the message means.
   - Decides if it is routine noise/heartbeat (IGNORE=1) or meaningful perception for the Noob (IGNORE=0).
   - If meaningful for the Noob, crafts a concise, meaningful status report message.
   - Synthesizes a regex pattern and registers it into PatternDB so future lines match instantly.
2. Every 10 minutes (configurable):
   - Reviews the 10-minute log window.
   - Emits timestamped diagnostic suggestions & warnings to suggestions.log, citing Aigel's start time.
3. Configurable log source:
   - file:<path>
   - command:<cmd>
   - journalctl:<args>
   - dmesg
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
from typing import Any

_AUTONOMY = Path(__file__).resolve().parents[2] / "common" / "autonomy"
if str(_AUTONOMY) not in sys.path:
    sys.path.insert(0, str(_AUTONOMY))
_SERVICE = Path(__file__).resolve().parent
if str(_SERVICE) not in sys.path:
    sys.path.insert(0, str(_SERVICE))

import sense as _sense
from aigel_think import QwenClient, QwenError
from pattern_db import PatternDB

LOGS_DIR = Path(__file__).resolve().parents[1] / "logs"
SUGGESTIONS_LOG = LOGS_DIR / "suggestions.log"
DIAGNOSTICS_LOG = LOGS_DIR / "diagnostics.log"

logger = logging.getLogger("aigel_perception_engine")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class LogSource:
    """Configurable reader for system or sensory logs."""

    def __init__(self, source_spec: str):
        self.spec = source_spec
        self.kind = "file"
        self.target = source_spec
        self._last_file_pos = 0

        if ":" in source_spec:
            prefix, rest = source_spec.split(":", 1)
            prefix = prefix.lower()
            if prefix in ("file", "command", "journalctl", "dmesg"):
                self.kind = prefix
                self.target = rest
        elif source_spec == "dmesg":
            self.kind = "dmesg"

    def read_lines(self) -> list[str]:
        if self.kind == "file":
            p = Path(self.target)
            if not p.is_file():
                return []
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                f.seek(self._last_file_pos)
                new_text = f.read()
                self._last_file_pos = f.tell()
            lines = [l.strip() for l in new_text.splitlines() if l.strip()]
            return lines

        elif self.kind == "command":
            try:
                res = subprocess.run(self.target, shell=True, capture_output=True, text=True, timeout=10)
                return [l.strip() for l in res.stdout.splitlines() if l.strip()]
            except Exception as e:
                logger.warning(f"Error running log command '{self.target}': {e}")
                return []

        elif self.kind == "journalctl":
            cmd = f"journalctl {self.target} --no-pager"
            try:
                res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
                return [l.strip() for l in res.stdout.splitlines() if l.strip()]
            except Exception as e:
                logger.warning(f"Error reading journalctl: {e}")
                return []

        elif self.kind == "dmesg":
            try:
                res = subprocess.run("dmesg | tail -n 150", shell=True, capture_output=True, text=True, timeout=5)
                return [l.strip() for l in res.stdout.splitlines() if l.strip()]
            except Exception as e:
                logger.warning(f"Error reading dmesg: {e}")
                return []

        return []


ANALYSIS_SYSTEM_PROMPT = """You are Aigel, Noobia's little diagnostics angel.
Your role: Observe log lines from a Noob (e.g. Lynx the phone).
When an unrecognized log line appears, you must analyze its meaning and decide:
1. Is it ROUTINE NOISE, a polling tick, a null sample, or a background heartbeat?
   -> Set "ignore": true, "message": null, "to_noob": false, "p": 0.
2. Is it a REAL PERCEPTION or PHYSICAL EVENT for the Noob (touch, motion, sound, camera sighting, temperature drop, battery charging)?
   -> Set "ignore": false, "to_noob": true, "p": 1.
   -> Provide a warm, concise status report "message" for the Noob (e.g. "You perceive: sudden vibration at 140 Hz.").
3. Is it a SYSTEM ANOMALY or WARNING (dropped events, thermal spike, hardware buffer overflow)?
   -> Set "ignore": false, "to_noob": true, "p": 2.
   -> Provide a helpful, concise status report "message" for the Noob (e.g. "Alert: touch panel dropped events due to buffer overflow.").

Return JSON only:
{
  "pattern_id": "<concise-slug-id-e.g.-motion-vibration-sudden>",
  "sense": "<sense_name_e.g._motion|touch|battery|sensorhub|system>",
  "event": "<event_name_e.g._vibration.sudden|charging.plugged|sync_poll>",
  "regex": "<escaped_regex_pattern_matching_this_line_family>",
  "ignore": <true_or_false>,
  "to_noob": <true_or_false>,
  "message": "<meaningful_short_status_report_or_null>",
  "p": <0|1|2>
}
"""


class AigelPerceptionEngine:
    def __init__(
        self,
        source: LogSource,
        host: str = "lynx",
        db: PatternDB | None = None,
        review_interval_s: int = 600,
        use_llm: bool = True,
    ):
        self.source = source
        self.host = host
        self.db = db or PatternDB()
        self.review_interval_s = review_interval_s
        self.use_llm = use_llm
        self.start_time = utc_now_iso()
        self.last_review_time = time.time()
        self.recent_window_lines: list[tuple[float, str]] = []  # (timestamp, line)
        self.client = QwenClient(timeout_s=30) if use_llm else None

    def find_matching_pattern(self, line: str, patterns: list[dict]) -> dict | None:
        """Find a pattern in the DB that matches this line."""
        parsed = _sense.parse_line(line)
        sense_name = parsed.get("sense") if parsed else None
        event_name = parsed.get("event") if parsed else None

        for p in patterns:
            # 1. Regex match
            reg = p.get("regex")
            if reg:
                try:
                    if re.search(reg, line):
                        return p
                except re.error:
                    pass

            # 2. Structured sense/event match
            m = p.get("match", {})
            if sense_name and m.get("sense") == sense_name:
                if not m.get("event") or m.get("event") == event_name:
                    text_contains = m.get("text_contains")
                    if text_contains and text_contains not in line:
                        continue
                    return p
        return None

    def analyze_unmatched_line_heuristic(self, line: str) -> dict:
        """Deterministic heuristic fallback when Qwen is not used or unavailable."""
        line_clean = line.strip()
        lower = line_clean.lower()

        # Check for noisy/ignore lines
        is_noisy = any(w in lower for w in [
            "sync_poll", "keepalive", "heartbeat", "idle_tick", "beacon_probe",
            "baseline_recalibrat", "status.sample raw=0", "i2c_bus_idle", "seq="
        ])
        is_warning = any(w in lower for w in [
            "warning", "dropped", "overflow", "elevated", "throttle", "timeout", "critical", "oom"
        ])

        parsed = _sense.parse_line(line_clean)
        sense_name = parsed.get("sense") if parsed else "system"
        event_name = parsed.get("event") if parsed else "event"

        if not parsed:
            # Try to extract tag from [bracket] or daemon name
            m_tag = re.search(r"\[([a-z0-9_-]+)\]\s*([a-z0-9_.-]+)", line_clean, re.I)
            if m_tag:
                sense_name = m_tag.group(1).lower()
                event_name = m_tag.group(2).lower()

        slug = f"{sense_name}-{event_name}".replace(".", "-").replace("_", "-")[:40]

        if is_noisy and not is_warning:
            # Construct a safe regex for noise
            escaped_words = re.escape(f"{sense_name}")
            return {
                "pattern_id": f"ignore-{slug}",
                "sense": sense_name,
                "event": event_name,
                "regex": rf"{escaped_words}.*{re.escape(event_name)}",
                "ignore": True,
                "to_noob": False,
                "message": None,
                "p": 0,
            }
        elif is_warning:
            return {
                "pattern_id": f"alert-{slug}",
                "sense": sense_name,
                "event": event_name,
                "regex": rf"{re.escape(sense_name)}.*{re.escape(event_name)}",
                "ignore": False,
                "to_noob": True,
                "message": f"Alert: {sense_name} reported {event_name.replace('_', ' ')}.",
                "p": 2,
            }
        else:
            # Meaningful perception
            clean_event = event_name.replace("_", " ").replace(".", " ")
            return {
                "pattern_id": f"sense-{slug}",
                "sense": sense_name,
                "event": event_name,
                "regex": rf"{re.escape(sense_name)}.*{re.escape(event_name)}",
                "ignore": False,
                "to_noob": True,
                "message": f"You perceive: {clean_event} ({sense_name}).",
                "p": 1,
            }

    def analyze_unmatched_line_qwen(self, line: str) -> dict:
        """Ask Qwen on Ollama to analyze the log line and synthesize a pattern."""
        if not self.client:
            return self.analyze_unmatched_line_heuristic(line)

        prompt = f"Analyze this log line from {self.host}:\n\"{line}\"\nSynthesize a pattern JSON."
        try:
            raw_reply = self.client.chat([
                {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ], max_tokens=512)

            # Extract JSON block
            m = re.search(r"\{.*\}", raw_reply, re.DOTALL)
            if m:
                data = json.loads(m.group(0))
                pid = str(data.get("pattern_id") or "unnamed-pattern").lower()
                pid = re.sub(r"[^a-z0-9_-]+", "-", pid).strip("-")[:45]
                return {
                    "pattern_id": pid,
                    "sense": str(data.get("sense") or "sensory")[:24],
                    "event": str(data.get("event") or "event")[:48],
                    "regex": data.get("regex") or rf"{re.escape(line[:25])}",
                    "ignore": bool(data.get("ignore")),
                    "to_noob": bool(data.get("to_noob")),
                    "message": data.get("message") if not bool(data.get("ignore")) else None,
                    "p": int(data.get("p") or (0 if data.get("ignore") else 1)),
                }
        except Exception as e:
            logger.info(f"Qwen synthesis fell back to heuristic: {e}")

        return self.analyze_unmatched_line_heuristic(line)

    def process_line(self, line: str, known_patterns: list[dict]) -> dict:
        """Process one line: match or learn."""
        now = time.time()
        self.recent_window_lines.append((now, line))

        # Check existing match
        match = self.find_matching_pattern(line, known_patterns)
        if match:
            self.db.record_hit(match["id"])
            if match.get("ignore"):
                return {"status": "matched_ignore", "pattern": match}
            return {"status": "matched_perception", "pattern": match, "message": match.get("message")}

        # Line is UNMATCHED -> Aigel analyzes and learns it
        analysis = self.analyze_unmatched_line_qwen(line) if self.use_llm else self.analyze_unmatched_line_heuristic(line)

        pat_to_insert = {
            "id": analysis["pattern_id"],
            "match": {"sense": analysis["sense"], "event": analysis["event"]},
            "regex": analysis["regex"],
            "message": analysis["message"],
            "ignore": analysis["ignore"],
            "to_noob": analysis["to_noob"],
            "p": analysis["p"],
            "cooldown_s": 0 if analysis["ignore"] else 300,
            "examples": {
                "must": [line],
                "must_not": [],
            },
        }

        self.db.upsert_pattern(pat_to_insert, host=self.host)
        # Add to local known_patterns cache so subsequent lines in same batch match instantly
        known_patterns.append({
            "id": pat_to_insert["id"],
            "match": pat_to_insert["match"],
            "regex": pat_to_insert["regex"],
            "message": pat_to_insert["message"],
            "ignore": pat_to_insert["ignore"],
            "to_noob": pat_to_insert["to_noob"],
            "p": pat_to_insert["p"],
        })

        return {
            "status": "learned_new_pattern",
            "pattern": pat_to_insert,
            "message": pat_to_insert["message"],
        }

    def run_10min_diagnostic_review(self) -> list[str]:
        """Perform the periodic diagnostic review of the recent log window."""
        now = time.time()
        cutoff = now - 600.0  # 10 minutes
        # Retain only items from the last 10 minutes
        self.recent_window_lines = [item for item in self.recent_window_lines if item[0] >= cutoff]
        lines = [item[1] for item in self.recent_window_lines]

        suggestions = []
        now_iso = utc_now_iso()

        # Analyze drop rates / overflows
        dropped_lines = [l for l in lines if "drop" in l.lower() or "overflow" in l.lower()]
        if dropped_lines:
            suggestions.append(
                f"[SUGGESTION/ALERT] Sensor/Touch event drops detected in {len(dropped_lines)} sample(s). "
                f"Consider increasing FIFO queues or event debouncing."
            )

        # Analyze thermals
        thermal_lines = [l for l in lines if "thermal" in l.lower() or "soc_mc=" in l.lower()]
        for l in thermal_lines:
            m = re.search(r"soc_mc=(\d+)", l)
            if m:
                mc = int(m.group(1))
                if mc >= 48000:
                    suggestions.append(f"[WARNING] SoC peak temperature observed at {mc/1000.0:.1f}°C. Soft throttle recommended.")
                    break

        # Analyze low battery
        power_lines = [l for l in lines if "battery" in l.lower() and ("low" in l.lower() or "critical" in l.lower())]
        if power_lines:
            suggestions.append(f"[WARNING] Battery low capacity observed in recent log window.")

        # If clean, note nominal state
        if not suggestions:
            suggestions.append("[NOMINAL] All monitored sensors and services operated within normal parameters.")

        # Write to suggestions.log
        SUGGESTIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(SUGGESTIONS_LOG, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*80}\n")
            f.write(f"[AIGEL 10-MINUTE DIAGNOSTIC REVIEW]\n")
            f.write(f"Aigel Service Started: {self.start_time}\n")
            f.write(f"Review Timestamp:      {now_iso}\n")
            f.write(f"Log Window Samples:    {len(lines)} lines\n")
            f.write(f"Suggestions & Observations:\n")
            for s in suggestions:
                f.write(f"  • {s}\n")
            f.write(f"{'='*80}\n")

        self.last_review_time = now
        return suggestions

    def step(self) -> dict[str, Any]:
        """Perform one scan cycle over new log lines."""
        new_lines = self.source.read_lines()
        known = self.db.get_top_ranker_patterns(self.host, limit=500)

        results = []
        for line in new_lines:
            res = self.process_line(line, known)
            results.append((line, res))

        # Check if periodic diagnostic review is due
        review_due = (time.time() - self.last_review_time) >= self.review_interval_s
        suggestions = []
        if review_due:
            suggestions = self.run_10min_diagnostic_review()

        return {
            "processed_count": len(new_lines),
            "results": results,
            "suggestions": suggestions,
            "review_ran": review_due,
        }

    def run_forever(self, poll_interval_s: float = 1.0):
        print(f"[{utc_now_iso()}] Aigel Perception Engine started for host '{self.host}'")
        print(f"  Source:           {self.source.spec}")
        print(f"  Service Started:  {self.start_time}")
        print(f"  Review Interval:  {self.review_interval_s}s")
        print(f"  Suggestions Log:  {SUGGESTIONS_LOG}\n", flush=True)

        while True:
            try:
                res = self.step()
                for line, r in res["results"]:
                    st = r["status"]
                    pat = r.get("pattern", {})
                    if st == "learned_new_pattern":
                        ign = "[IGNORE=1]" if pat.get("ignore") else "[REPORT]"
                        print(f"[{utc_now_iso()}] LEARNED {ign} id={pat.get('id')} -> msg: {r.get('message')}")
                    elif st == "matched_perception":
                        print(f"[{utc_now_iso()}] PERCEIVED id={pat.get('id')} -> msg: {r.get('message')}")

                if res["review_ran"]:
                    print(f"[{utc_now_iso()}] 10-Minute Diagnostic Review completed ({len(res['suggestions'])} items).")

            except Exception as e:
                print(f"[{utc_now_iso()}] Engine error: {e}", file=sys.stderr)

            time.sleep(poll_interval_s)


def main():
    parser = argparse.ArgumentParser(description="Aigel Perception & Diagnostics Engine")
    parser.add_argument("--source", "-s", required=True, help="Log source: file:<path>, command:<cmd>, or dmesg")
    parser.add_argument("--host", default="lynx", help="Host name (default: lynx)")
    parser.add_argument("--db-path", default=None, help="Custom pattern DB path")
    parser.add_argument("--review-interval-s", type=int, default=600, help="Diagnostic review interval in seconds (default: 600)")
    parser.add_argument("--no-llm", action="store_true", help="Disable Qwen, use fast deterministic heuristic")
    parser.add_argument("--once", action="store_true", help="Process available lines once and exit")
    parser.add_argument("--poll-interval", type=float, default=1.0, help="Poll interval in seconds (default: 1.0)")
    args = parser.parse_args()

    src = LogSource(args.source)
    db = PatternDB(args.db_path)
    engine = AigelPerceptionEngine(
        source=src,
        host=args.host,
        db=db,
        review_interval_s=args.review_interval_s,
        use_llm=not args.no_llm,
    )

    if args.once:
        res = engine.step()
        print(f"Processed {res['processed_count']} lines.")
        for line, r in res["results"]:
            print(f"  {r['status']}: {r.get('pattern', {}).get('id')} -> {r.get('message')}")
        if not res["review_ran"]:
            # Force review on --once if requested to verify diagnostic output
            suggs = engine.run_10min_diagnostic_review()
            print(f"Diagnostic review output ({len(suggs)} items):")
            for s in suggs:
                print(f"  {s}")
    else:
        engine.run_forever(poll_interval_s=args.poll_interval)


if __name__ == "__main__":
    main()
