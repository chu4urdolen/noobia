#!/usr/bin/env python3
"""lynx-heat-report: digest lynx-heat-recorder JSONL into a short text report.

Runs anywhere (Nexus or Lynx). Prints, for one heat-*.jsonl file:
- span, sample count, start/end/max of the hottest zones and battery temp;
- battery capacity and mean current (drain mA, + = charging), charger state;
- per-cluster frequency (mean, % of samples at max) and system CPU %;
- the processes using the most CPU overall (summed over samples);
- the last N samples in one line each (for "what happened at the end").

    lynx_heat_report.py FILE.jsonl [--tail 12]
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
import sys
import time

KEY_ZONES = ("soc_max", "cpu_bigbig1", "cpu_bigbig2", "cpu_little1", "gpu1", "md1", "soc_mm")


def load(path):
    rows = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass  # a torn last line after a power cut
    return rows


def hhmm(t):
    return time.strftime("%H:%M:%S", time.gmtime(t)) + "Z"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--tail", type=int, default=12)
    a = ap.parse_args(argv)
    rows = load(a.file)
    if not rows:
        print("no samples")
        return 1
    out = [f"file: {a.file}", f"samples: {len(rows)}  span: {hhmm(rows[0]['t'])} -> {hhmm(rows[-1]['t'])} "
           f"({(rows[-1]['t'] - rows[0]['t']) / 60:.1f} min)"]
    out.append("temperatures C (start / end / max):")
    for z in KEY_ZONES:
        vals = [r["thermal"]["zones"].get(z) for r in rows if r.get("thermal")]
        vals = [v for v in vals if isinstance(v, int)]
        if vals:
            out.append(f"  {z:12s} {vals[0]/1000:5.1f} / {vals[-1]/1000:5.1f} / {max(vals)/1000:5.1f}")
    bt = [r["battery"].get("temp_mC") for r in rows if r.get("battery", {}).get("temp_mC") is not None]
    if bt:
        out.append(f"  {'battery':12s} {bt[0]/1000:5.1f} / {bt[-1]/1000:5.1f} / {max(bt)/1000:5.1f}")
    caps = [r["battery"].get("capacity") for r in rows if r.get("battery", {}).get("capacity") is not None]
    cur = [r["battery"].get("current_ma") for r in rows if r.get("battery", {}).get("current_ma") is not None]
    chg = sum(1 for r in rows if r.get("battery", {}).get("charger"))
    if caps:
        out.append(f"battery: {caps[0]}% -> {caps[-1]}%  mean current {sum(cur)/max(len(cur),1):.0f} mA  "
                   f"charger on in {100*chg/len(rows):.0f}% of samples")
    cpu = [r.get("cpu_pct") for r in rows if r.get("cpu_pct") is not None]
    out.append(f"system cpu: mean {sum(cpu)/max(len(cpu),1):.1f}%  max {max(cpu) if cpu else 0:.1f}%")
    pol = defaultdict(list)
    for r in rows:
        for k, v in (r.get("freq_khz") or {}).items():
            if v:
                pol[k].append(v)
    for k, v in sorted(pol.items()):
        top = max(v)
        out.append(f"  {k}: mean {sum(v)/len(v)/1e6:.2f} GHz, at its max ({top/1e6:.2f}) {100*v.count(top)/len(v):.0f}% of samples")
    procs = defaultdict(float)
    for r in rows:
        for p in r.get("top", []):
            procs[p["name"]] += p["cpu"]
    out.append("top cpu users (sum of % over samples / samples = mean %):")
    for name, s in sorted(procs.items(), key=lambda kv: -kv[1])[:10]:
        out.append(f"  {name:32s} mean {s/len(rows):5.1f}%")
    out.append(f"last {a.tail} samples:")
    for r in rows[-a.tail:]:
        z = r.get("thermal", {}).get("zones", {})
        b = r.get("battery", {})
        tops = ",".join(f"{p['name']}:{p['cpu']:.0f}" for p in r.get("top", [])[:3])
        out.append(f"  {hhmm(r['t'])} soc={z.get('soc_max',0)/1000:.1f} bb={z.get('cpu_bigbig1',0)/1000:.1f} "
                   f"bat={b.get('temp_mC',0)/1000:.1f}C {b.get('capacity')}% {b.get('current_ma')}mA "
                   f"cpu={r.get('cpu_pct')}% cool={r.get('thermal',{}).get('cooling')} top={tops}")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
