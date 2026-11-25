#!/usr/bin/env python3
"""S13 cellular and location sense for Lynx.

Rose's backlog (Gwyn, 2026-11-25, picked up from Banshee):

    cell  tower.discovered      LNX-26 / LNX-05  a cell (serving or neighbour) she never saw
    cell  handover              LNX-27 / LNX-06  the serving cell changed
    cell  technology.change     LNX-28 / LNX-07  LTE <-> 5G NSA <-> 5G SA <-> 3G/2G
    cell  signal.change         LNX-29 / LNX-04  RSRP moved to another band (2 samples)
    cell  registration.change   LNX-36           registered / roaming / searching / denied / none
    cell  data.usage            LNX-12           every 100 MB of mobile data (ccmni counters)
    location  change            LNX-34 / LNX-10  she moved more than 50 m
    + LNX-11: with a fix and a measurement, one row per sample goes to the coverage
      map /var/lib/noobia/cellmap.db (table cell_obs, Bee's style: ts, lat, lon, ...)

**Rose's rules 1-3: this sense never touches the modem.** It reads two RAM files
that the modem and GNSS services write (Aria's LNX-01..03 and the GNSS bring-up),
plus the kernel's ccmni byte counters. Until those services exist the sense is
quiet and honest: ``source: none``. Contract (all fields optional except t):

    /run/lynx/cell.json  {"t": 1764000000, "registration": "registered", "operator": "A1",
                          "rat": "LTE|NR-NSA|NR-SA|WCDMA|GSM",
                          "serving": {"id": "284-01-1234-56789", "pci": 101, "earfcn": 1850,
                                      "band": 3, "rsrp": -95, "rsrq": -11, "sinr": 12, "rssi": -65},
                          "neighbors": [{"id": "...", "pci": 202, "earfcn": 1850, "rsrp": -104}]}
    /run/lynx/gnss.json  {"t": 1764000000, "fix": true, "lat": 42.69, "lon": 23.32, "acc_m": 8}

A file older than 120 s counts as absent.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import sqlite3
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from lynx_sense_kit import Event, band, run_sense  # noqa: E402
from lynx_senses_lib import finish  # noqa: E402

CELL_FILE = Path(os.environ.get("LYNX_CELL_FILE", "/run/lynx/cell.json"))
GNSS_FILE = Path(os.environ.get("LYNX_GNSS_FILE", "/run/lynx/gnss.json"))
CELLMAP = Path(os.environ.get("LYNX_CELLMAP_DB", "/var/lib/noobia/cellmap.db"))
NET = Path("/sys/class/net")
STALE_S = 120
MOVE_M = 50.0
USAGE_STEP = 100 * 1_000_000
# RSRP dBm: excellent > -80, good -80..-90, fair -90..-100, poor -100..-110, none below
RSRP_BANDS = [("none", -110), ("poor", -100), ("fair", -90), ("good", -80), ("excellent", None)]
RAT_NAMES = {"LTE": "4G LTE", "NR-NSA": "5G (NSA, on an LTE anchor)", "NR-SA": "5G standalone",
             "WCDMA": "3G", "GSM": "2G"}


def read_fresh(path: Path, now: float) -> dict | None:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or now - float(data.get("t", 0)) > STALE_S:
        return None
    return data


def ccmni_bytes(net: Path = NET) -> int:
    total = 0
    for d in net.glob("ccmni*"):
        for k in ("rx_bytes", "tx_bytes"):
            try:
                total += int((d / "statistics" / k).read_text())
            except (OSError, ValueError):
                pass
    return total


def observe(now: float | None = None) -> dict:
    now = now or time.time()
    return {"cell": read_fresh(CELL_FILE, now), "gnss": read_fresh(GNSS_FILE, now),
            "bytes": ccmni_bytes()}


def metres(a, b) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371000.0 * 2 * math.asin(math.sqrt(h))


def _cell_key(c: dict) -> str | None:
    if not isinstance(c, dict):
        return None
    if c.get("id"):
        return str(c["id"])
    if c.get("pci") is not None:
        return f"pci{c['pci']}@{c.get('earfcn', '?')}"
    return None


def detect_cell(prev: dict, obs: dict, now: float):
    ev, cell = [], obs["cell"]
    state = {"t": now, "known": list(prev.get("known", []))[-500:]}

    # LNX-12 data usage works without a modem service: the kernel counters.
    total = int(prev.get("usage_total", 0))
    last = prev.get("bytes_last")
    b = obs["bytes"]
    if isinstance(last, int):
        total += b - last if b >= last else b        # counters reset on reboot
    state.update(bytes_last=b, usage_total=total)
    step = int(prev.get("usage_step", total // USAGE_STEP))
    if total // USAGE_STEP > step:
        ev.append(Event("data.usage", {"mb": total // 1_000_000},
                        f"I have used {total // 1_000_000} MB of mobile data so far.", priority=5))
    state["usage_step"] = max(step, total // USAGE_STEP)

    if cell is None:
        state.update({k: prev.get(k) for k in ("registration", "rat", "serving", "rsrp_band")})
        state["source"] = "none"
        return ev, state
    state["source"] = "cell.json"
    base = prev.get("source") == "cell.json"
    reg, rat = cell.get("registration"), cell.get("rat")
    serving = cell.get("serving") or {}
    skey = _cell_key(serving)

    if base and reg and reg != prev.get("registration"):
        ev.append(Event("registration.change", {"registration": reg, "was": prev.get("registration"),
                                                "operator": cell.get("operator", "")},
                        f"My cellular registration changed: {prev.get('registration')} -> {reg}"
                        + (f" on {cell['operator']}." if cell.get("operator") else "."), priority=3))
    if base and rat and prev.get("rat") and rat != prev["rat"]:
        ev.append(Event("technology.change", {"rat": rat, "was": prev["rat"]},
                        f"My mobile network switched from {RAT_NAMES.get(prev['rat'], prev['rat'])} "
                        f"to {RAT_NAMES.get(rat, rat)}.", priority=5))
    if base and skey and prev.get("serving") and skey != prev["serving"]:
        ev.append(Event("handover", {"cell": skey, "was": prev["serving"], "rat": rat or ""},
                        f"Handover: my phone moved from cell {prev['serving']} to {skey}.", priority=5))
    known = set(state["known"])
    cells = [serving] + [n for n in cell.get("neighbors") or [] if isinstance(n, dict)]
    for c in cells:
        k = _cell_key(c)
        if k and k not in known:
            known.add(k)
            state["known"].append(k)
            if base:
                role = "serving" if c is serving else "neighbour"
                ev.append(Event("tower.discovered", {"cell": k, "role": role, "rsrp": c.get("rsrp", "")},
                                f"I see a cell tower I never saw before: {k} ({role}"
                                + (f", {c['rsrp']} dBm)." if c.get("rsrp") is not None else ")."),
                                priority=5))
    rsrp = serving.get("rsrp")
    rb = band(rsrp, RSRP_BANDS, prev.get("rsrp_band"), hysteresis=3) if isinstance(rsrp, (int, float)) else None
    seen = ((prev.get("rb_seen") or []) + [rb])[-2:]
    believed = prev.get("rsrp_band")
    if base and rb and len(seen) == 2 and seen[0] == seen[1] == rb and believed and rb != believed:
        ev.append(Event("signal.change", {"band": rb, "was": believed, "rsrp": rsrp,
                                          "sinr": serving.get("sinr", "")},
                        f"My mobile signal is now {rb} ({rsrp} dBm RSRP"
                        + (f", SINR {serving['sinr']} dB)." if serving.get("sinr") is not None else ")."),
                        priority=5))
        believed = rb
    state.update(registration=reg, rat=rat, serving=skey, rsrp_band=believed or rb, rb_seen=seen)
    return ev, state


def detect_location(prev: dict, obs: dict, now: float):
    g = obs["gnss"]
    if not g or not g.get("fix") or g.get("lat") is None:
        return [], {k: prev.get(k) for k in ("lat", "lon")} | {"fix": False}
    here = (float(g["lat"]), float(g["lon"]))
    state = {"lat": here[0], "lon": here[1], "fix": True}
    if prev.get("lat") is None:
        return [], state
    d = metres((prev["lat"], prev["lon"]), here)
    if d < MOVE_M:
        return [], {"lat": prev["lat"], "lon": prev["lon"], "fix": True}
    return [Event("change", {"lat": round(here[0], 5), "lon": round(here[1], 5), "moved_m": int(d)},
                  f"I moved about {int(d)} m.", priority=5)], state


def record_coverage(obs: dict, now: float, db: Path = CELLMAP) -> bool:
    """LNX-11: one coverage row when a fix and a measurement are both present."""
    g, c = obs.get("gnss"), obs.get("cell")
    if not (g and g.get("fix") and c and isinstance(c.get("serving"), dict)):
        return False
    s = c["serving"]
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db), timeout=2)
    try:
        con.execute("CREATE TABLE IF NOT EXISTS cell_obs (id INTEGER PRIMARY KEY, ts INTEGER NOT NULL,"
                    " lat REAL, lon REAL, acc_m REAL, rat TEXT, operator TEXT, cell TEXT, pci INTEGER,"
                    " earfcn INTEGER, band INTEGER, rsrp REAL, rsrq REAL, sinr REAL, rssi REAL,"
                    " registration TEXT, src TEXT)")
        con.execute("INSERT INTO cell_obs (ts, lat, lon, acc_m, rat, operator, cell, pci, earfcn, band,"
                    " rsrp, rsrq, sinr, rssi, registration, src) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (int(now), g.get("lat"), g.get("lon"), g.get("acc_m"), c.get("rat"), c.get("operator"),
                     _cell_key(s), s.get("pci"), s.get("earfcn"), s.get("band"), s.get("rsrp"),
                     s.get("rsrq"), s.get("sinr"), s.get("rssi"), c.get("registration"), "lynx"))
        con.commit()
    finally:
        con.close()
    return True


def run(dry_run: bool = False, state_file: str | None = None, now=None, sense_mod=None, observer=None):
    t = float(now if now is not None else time.time())
    snap = {}

    def once():
        if not snap:
            snap.update((observer or (lambda: observe(t)))())
        return snap

    cell, code = run_sense("cell", once, detect_cell, dry_run=dry_run, state_file=state_file,
                           now=t, sense_mod=sense_mod)
    loc_state = str(Path(state_file).with_name("location.json")) if state_file else None
    loc, code2 = run_sense("location", once, detect_location, dry_run=dry_run, state_file=loc_state,
                           now=t, sense_mod=sense_mod)
    if snap and not dry_run:
        try:
            record_coverage(snap, t)
        except (OSError, sqlite3.Error):
            pass
    out = dict(cell)
    out["emitted"] = list(cell.get("emitted", [])) + list(loc.get("emitted", []))
    out["source"] = "cell.json" if snap.get("cell") else "none"
    out["gnss"] = bool(snap.get("gnss"))
    out["ok"] = bool(cell.get("ok")) and bool(loc.get("ok"))
    return out, max(code, code2)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    return finish(*run(dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
