#!/usr/bin/env python3
"""lynx-heat-correlate: what each of Lynx's actions costs in heat and battery.

Joins lynx-heat-recorder samples (JSONL, 5 s) with Lynx's agent audit log
(/var/log/lynx-agent.jsonl: {"time", "event": "tool"|"backend", "name"}) and
prints, per tool (and per model call), averaged over every occurrence:

- dT_soc  : soc_max in the window AFTER the call minus the window BEFORE (C)
- peak    : highest soc_max seen in the after-window (C)
- I_after : mean battery current in the after-window (mA, negative = drain)
- dI      : I_after minus mean current in the before-window (mA)

Overlapping actions blur this, so it is a first-order picture, not proof.
Also prints the idle baseline (samples with no action within 60 s).

    lynx_heat_correlate.py HEAT.jsonl AGENT.jsonl [--since T] [--before 15] [--after 30]
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import sys


def load_jsonl(path):
    out = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


def soc(r):
    return (r.get("thermal", {}).get("zones", {}).get("soc_max") or 0) / 1000.0


def cur(r):
    return r.get("battery", {}).get("current_ma")


def window(samples, t0, t1):
    return [s for s in samples if t0 <= s["t"] < t1]


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("heat")
    ap.add_argument("agent")
    ap.add_argument("--since", type=float, default=0.0)
    ap.add_argument("--before", type=float, default=15.0)
    ap.add_argument("--after", type=float, default=30.0)
    a = ap.parse_args(argv)
    heat = sorted((r for r in load_jsonl(a.heat) if r.get("t", 0) >= a.since), key=lambda r: r["t"])
    events = [e for e in load_jsonl(a.agent)
              if e.get("time", 0) >= a.since and e.get("event") in ("tool", "backend")]
    if not heat:
        print("no heat samples in range")
        return 1
    stats = defaultdict(lambda: {"n": 0, "dT": [], "peak": [], "I": [], "dI": []})
    for e in events:
        name = e.get("name") if e["event"] == "tool" else f"model:{e.get('model', '?')}"
        if e["event"] == "tool" and e.get("ok") is False:
            name += " (failed)"
        t = e["time"]
        pre, post = window(heat, t - a.before, t), window(heat, t, t + a.after)
        if not pre or not post:
            continue
        s = stats[name]
        s["n"] += 1
        s["dT"].append(mean(soc(r) for r in post) - mean(soc(r) for r in pre))
        s["peak"].append(max(soc(r) for r in post))
        ia, ib = mean(cur(r) for r in post), mean(cur(r) for r in pre)
        s["I"].append(ia)
        if ia is not None and ib is not None:
            s["dI"].append(ia - ib)
    times = [e["time"] for e in events]
    idle = [r for r in heat if all(abs(r["t"] - t) > 60 for t in times)]
    span = (heat[-1]["t"] - heat[0]["t"]) / 60
    print(f"heat samples: {len(heat)} over {span:.1f} min; actions: {len(events)}")
    if idle:
        print(f"idle baseline ({len(idle)} samples, no action within 60 s): "
              f"soc {mean(soc(r) for r in idle):.1f} C, current {mean(cur(r) for r in idle):.0f} mA")
    print(f"{'action':34s} {'n':>3s} {'dT_soc':>7s} {'peak':>6s} {'I_after':>8s} {'dI':>7s}")
    for name, s in sorted(stats.items(), key=lambda kv: -(mean(kv[1]["dT"]) or 0)):
        def f(x, w, d=1):
            return f"{x:{w}.{d}f}" if x is not None else " " * (w - 1) + "-"
        print(f"{name:34s} {s['n']:3d} {f(mean(s['dT']), 7)} {f(max(s['peak']), 6)} "
              f"{f(mean(s['I']), 8, 0)} {f(mean(s['dI']), 7, 0)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
