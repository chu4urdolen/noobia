#!/usr/bin/env python3
"""Lynx Observability Pipeline Logger and Stream Inspector.

Tracks the complete autonomy and cognition lifecycle:
1. Raw sense lines & Chunker states (priority, timeout, volume)
2. Ranker pattern evaluations & matched templates
3. Delivered prompts into Lynx's agent queue (SENSE, CHAT)
4. Model inference, tool calls with arguments, vocal speech, and execution latency

Log location: /var/log/lynx/stream.jsonl (fallback: /tmp/lynx-stream.jsonl)
CLI Tool: lynx-stream-log [-n N] [-f] [--json] [--stats]
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

DEFAULT_LOG_PATHS = [
    Path("/var/log/lynx/stream.jsonl"),
    Path("/var/log/lynx-stream.jsonl"),
    Path(os.environ.get("NOOBIA", "/noobia")) / "lynx" / "logs" / "stream.jsonl",
    Path("/tmp/lynx-stream.jsonl"),
]


def get_log_file() -> Path:
    for p in DEFAULT_LOG_PATHS:
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            if p.exists() or os.access(str(p.parent), os.W_OK):
                return p
        except Exception:
            continue
    return Path("/tmp/lynx-stream.jsonl")


def log_event(stage: str, data: dict[str, Any]) -> None:
    """Atomic structured append to the pipeline stream log."""
    now = time.time()
    iso = datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    record = {
        "ts": now,
        "iso": iso,
        "stage": stage,
        **data,
    }
    try:
        log_file = get_log_file()
        line = json.dumps(record, separators=(",", ":")) + "\n"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def format_event(record: dict[str, Any]) -> str:
    """Render a colored/formatted human-readable representation of a pipeline event."""
    stage = record.get("stage", "unknown")
    iso = record.get("iso", "")
    t_str = iso.split("T")[-1].replace("Z", "") if "T" in iso else str(record.get("ts", ""))

    lines = []
    if stage == "chunk_closed":
        reason = record.get("reason", "unknown")
        count = record.get("lines_count", 0)
        lines.append(f"\033[1;36m[{t_str}] 📦 CHUNK CLOSED\033[0m reason=\033[1m{reason}\033[0m lines={count}")
        raw_lines = record.get("raw_lines", [])
        if raw_lines:
            for rl in raw_lines[:4]:
                lines.append(f"  \033[2mraw:\033[0m {rl}")
            if len(raw_lines) > 4:
                lines.append(f"  \033[2m... and {len(raw_lines)-4} more raw lines\033[0m")
        explained = record.get("explained", [])
        if explained:
            pids = [e.get("pattern_id") for e in explained if isinstance(e, dict)]
            lines.append(f"  \033[32m✔ Matched Patterns:\033[0m {', '.join(filter(None, pids))}")
        unexplained = record.get("unexplained", [])
        if unexplained:
            lines.append(f"  \033[33m? Unexplained Lines:\033[0m {len(unexplained)}")
        rendered = record.get("rendered_text")
        if rendered:
            lines.append(f"  \033[1;32m➜ Delivered Text:\033[0m \"{rendered}\"")

    elif stage == "job_queued":
        jid = str(record.get("job_id", ""))[:8]
        kind = record.get("kind", "")
        prompt = record.get("prompt", "")
        lines.append(f"\033[1;35m[{t_str}] 📬 JOB QUEUED\033[0m id=#{jid} kind={kind}")
        lines.append(f"  \033[2mprompt:\033[0m {prompt}")

    elif stage == "agent_executed":
        kind = record.get("input_kind", "")
        duration = record.get("duration_s", 0.0)
        model = record.get("model", "")
        prompt = record.get("prompt", "")
        lines.append(f"\033[1;32m[{t_str}] 🧠 LYNX REACTION\033[0m [{kind}] model={model} ({duration:.2f}s)")
        lines.append(f"  \033[2minput:\033[0m \"{prompt}\"")
        calls = record.get("calls", [])
        if calls:
            for c in calls:
                name = c.get("name", "")
                args = json.dumps(c.get("arguments", {}))
                ok = c.get("ok", True)
                ok_str = "\033[32mok\033[0m" if ok else "\033[31mfailed\033[0m"
                lines.append(f"  \033[34m⚡ Tool Call:\033[0m \033[1m{name}\033[0m({args}) -> {ok_str}")
        speech = record.get("speech")
        if speech:
            lines.append(f"  \033[1;33m🗣 Spoke Aloud:\033[0m \033[1m\"{speech}\"\033[0m")
        thought = record.get("thought")
        if thought and thought != speech:
            lines.append(f"  \033[2mthought:\033[0m {thought}")

    elif stage == "tool_diagnostic":
        action = record.get("action", "")
        sentence = record.get("sentence", "")
        forked = record.get("forked", False)
        mode = "background" if forked else "sync"
        lines.append(f"\033[1;34m[{t_str}] 🛠 DIAGNOSTIC EXECUTION\033[0m action={action} mode={mode}")
        lines.append(f"  \033[32mresult:\033[0m \"{sentence}\"")

    else:
        lines.append(f"[{t_str}] {stage}: {json.dumps(record)}")

    return "\n".join(lines)


def read_records(log_file: Path, limit: int = 15) -> list[dict[str, Any]]:
    if not log_file.exists():
        return []
    records = []
    try:
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except Exception:
                        pass
    except Exception:
        pass
    return records[-limit:] if limit > 0 else records


def follow_records(log_file: Path, raw_json: bool = False) -> None:
    """Follow new records in real time (like tail -f)."""
    if not log_file.exists():
        print(f"Waiting for {log_file} to be created...")
        while not log_file.exists():
            time.sleep(0.5)

    with open(log_file, "r", encoding="utf-8", errors="replace") as f:
        f.seek(0, os.SEEK_END)
        while True:
            line = f.readline()
            if line:
                line = line.strip()
                if line:
                    try:
                        rec = json.loads(line)
                        if raw_json:
                            print(line)
                        else:
                            print(format_event(rec))
                            print("-" * 60)
                    except Exception:
                        print(line)
            else:
                time.sleep(0.2)


def print_stats(log_file: Path) -> None:
    records = read_records(log_file, limit=0)
    stages = {}
    reasons = {}
    patterns = {}
    tools = {}
    durations = []

    for r in records:
        st = r.get("stage", "unknown")
        stages[st] = stages.get(st, 0) + 1
        if st == "chunk_closed":
            reasons[r.get("reason", "")] = reasons.get(r.get("reason", ""), 0) + 1
            for exp in r.get("explained", []):
                pid = exp.get("pattern_id") if isinstance(exp, dict) else None
                if pid:
                    patterns[pid] = patterns.get(pid, 0) + 1
        elif st == "agent_executed":
            d = r.get("duration_s")
            if d:
                durations.append(float(d))
            for c in r.get("calls", []):
                cname = c.get("name", "")
                tools[cname] = tools.get(cname, 0) + 1

    print("\033[1;36m=== Lynx Observability Pipeline Statistics ===\033[0m")
    print(f"Total Logged Events: {len(records)}")
    print("\n\033[1mStages:\033[0m")
    for k, v in stages.items():
        print(f"  {k}: {v}")
    if reasons:
        print("\n\033[1mChunk Closure Reasons:\033[0m")
        for k, v in reasons.items():
            print(f"  {k}: {v}")
    if patterns:
        print("\n\033[1mTop Matched Sense Patterns:\033[0m")
        for k, v in sorted(patterns.items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f"  {k}: {v}")
    if tools:
        print("\n\033[1mAgent Tool Invocations:\033[0m")
        for k, v in sorted(tools.items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f"  {k}: {v}")
    if durations:
        avg = sum(durations) / len(durations)
        print(f"\n\033[1mAverage Inference Latency:\033[0m {avg:.2f}s (min: {min(durations):.2f}s, max: {max(durations):.2f}s)")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-n", "--lines", type=int, default=10, help="Number of recent events to display (default: 10)")
    parser.add_argument("-f", "--follow", action="store_true", help="Follow stream live in real time")
    parser.add_argument("--json", action="store_true", help="Output raw JSON records")
    parser.add_argument("--stats", action="store_true", help="Display summary statistics")
    parser.add_argument("--clear", action="store_true", help="Clear the pipeline stream log")
    args = parser.parse_args()

    log_file = get_log_file()

    if args.clear:
        if log_file.exists():
            log_file.write_text("")
            print(f"Cleared {log_file}")
        return

    if args.stats:
        print_stats(log_file)
        return

    if args.follow:
        follow_records(log_file, raw_json=args.json)
        return

    records = read_records(log_file, limit=args.lines)
    if not records:
        print(f"No pipeline stream events found in {log_file}.")
        return

    for r in records:
        if args.json:
            print(json.dumps(r))
        else:
            print(format_event(r))
            print("-" * 60)


if __name__ == "__main__":
    main()
