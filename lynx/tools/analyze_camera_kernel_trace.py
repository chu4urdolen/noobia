#!/usr/bin/env python3
"""Summarize one captured Lynx camera kernel trial without touching Lynx."""

import argparse
from collections import Counter
import json
from pathlib import Path
import re

KMSG = re.compile(r"^\d+,\d+,(\d+),[^;]*;(.*)$")
MODULE = "[mtk_cam_isp]"


def analyze(path):
    events = []
    counts = Counter()
    first = {}
    for number, line in enumerate(path.open(errors="replace"), 1):
        match = KMSG.match(line)
        if not match:
            continue
        usec, message = int(match.group(1)), match.group(2).strip()
        kind = None
        if MODULE in message and "calling  init_module" in message:
            kind = "isp_init_start"
        elif MODULE in message and "initcall init_module" in message and "returned" in message:
            kind = "isp_init_return"
        elif "mtk_cam_master_bind success" in message:
            kind = "isp_master_bound"
        elif "rcu_preempt detected stalls" in message:
            kind = "rcu_stall"
        elif "seninf_csi_port_" in message and "Failed to read efuse data" in message:
            kind = "csi_efuse_read_failure"
        elif "lbat_service: failed to get bat_h irq, ret=-517" in message:
            kind = "battery_irq_probe_defer"
        if kind:
            counts[kind] += 1
            event = {"kind": kind, "line": number, "timestamp_us": usec,
                     "message": message[:240]}
            first.setdefault(kind, event)
            if kind not in ("battery_irq_probe_defer", "csi_efuse_read_failure"):
                events.append(event)
    return {
        "source": str(path),
        "counts": dict(counts),
        "first": first,
        "timeline": events[:40],
        "intervals_seconds": {
            "isp_init_duration": round((first["isp_init_return"]["timestamp_us"] -
                                        first["isp_init_start"]["timestamp_us"]) / 1e6, 3)
            if "isp_init_start" in first and "isp_init_return" in first else None,
            "init_return_to_first_rcu_stall": round((first["rcu_stall"]["timestamp_us"] -
                                                     first["isp_init_return"]["timestamp_us"]) / 1e6, 3)
            if "isp_init_return" in first and "rcu_stall" in first else None,
        },
        "battery_irq_defer_precedes_isp": (
            first["battery_irq_probe_defer"]["timestamp_us"] <
            first["isp_init_start"]["timestamp_us"]
            if "battery_irq_probe_defer" in first and "isp_init_start" in first else None),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kernel_log", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = analyze(args.kernel_log)
    payload = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(payload)
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
