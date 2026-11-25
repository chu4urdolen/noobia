#!/usr/bin/env python3
"""S14 Bluetooth sense for Lynx: ``bluetooth device.discovered`` (LNX-30).

Rose's backlog (Gwyn, 2026-11-25, picked up from Banshee). Passive: it never
scans. It reads what bluetoothd already knows (D-Bus ObjectManager, one
``dbus-send`` call) and reports a device the first time it appears: found by
an on-demand scan (``lynx-netintel ble-scan``, LNX-18), by a device connecting
to her, or by a pairing. Aria's BLE GATT link to Nexus is never touched.

Names and addresses come from radio packets anyone can send: untrusted text
(Rose's rule 6), cleaned before it reaches a sense line.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from lynx_sense_kit import Event, run_sense  # noqa: E402
from lynx_senses_lib import finish  # noqa: E402

DBUS = ["dbus-send", "--system", "--print-reply", "--dest=org.bluez", "/",
        "org.freedesktop.DBus.ObjectManager.GetManagedObjects"]
_OBJ = re.compile(r'^\s*object path "([^"]+)"')
_KEY = re.compile(r'^\s*string "([A-Za-z]+)"\s*$')
_VAL = re.compile(r'^\s*variant\s+(string|boolean|int16|uint16|int32|uint32|byte)\s+"?(.*?)"?\s*$')
KEEP = {"Address", "AddressType", "Name", "Alias", "RSSI", "Paired", "Connected", "Trusted",
        "Icon", "Class", "Appearance", "Powered", "Discovering"}


def parse_objects(text: str) -> dict:
    """object path -> {property: value} for the simple-typed properties we keep."""
    objs, cur, key = {}, None, None
    for line in text.splitlines():
        m = _OBJ.match(line)
        if m:
            cur = objs.setdefault(m.group(1), {})
            key = None
            continue
        m = _KEY.match(line)
        if m and cur is not None:
            key = m.group(1)
            continue
        m = _VAL.match(line)
        if m and cur is not None and key in KEEP:
            kind, val = m.groups()
            if kind == "boolean":
                val = val == "true"
            elif kind != "string":
                try:
                    val = int(val)
                except ValueError:
                    pass
            cur.setdefault(key, val)
            key = None
    return objs


def devices(objs: dict) -> dict:
    """address -> properties, for device objects (…/hciN/dev_XX_XX…)."""
    out = {}
    for path, props in objs.items():
        if "/dev_" in path and props.get("Address"):
            out[props["Address"].upper()] = props
    return out


def observe() -> dict:
    r = subprocess.run(DBUS, capture_output=True, text=True, timeout=6)
    if r.returncode != 0:
        raise RuntimeError("bluetoothd not answering on D-Bus: " + r.stderr.strip()[:120])
    objs = parse_objects(r.stdout)
    adapter = next((p for k, p in objs.items() if re.fullmatch(r"/org/bluez/hci\d+", k)), {})
    return {"devices": devices(objs), "powered": bool(adapter.get("Powered"))}


def describe(addr: str, p: dict) -> str:
    name = p.get("Name") or p.get("Alias")
    if name and name.replace("-", ":").upper() == addr:
        name = None
    kind = "Bluetooth LE" if p.get("AddressType") == "random" else "Bluetooth"
    bits = [f"a {kind} device" + (f" called \"{name[:40]}\"" if name else " with no name"),
            f"({addr})"]
    if isinstance(p.get("RSSI"), int):
        bits.append(f"at {p['RSSI']} dBm")
    if p.get("Connected"):
        bits.append("connected to me")
    return "I noticed " + " ".join(bits) + "."


def detect(prev: dict, obs: dict, now: float):
    known = dict(prev.get("known", {}))
    events = []
    for addr, p in sorted(obs["devices"].items()):
        if addr not in known:
            if "known" in prev:
                events.append(Event("device.discovered",
                                    {"addr": addr, "rssi": p.get("RSSI", ""),
                                     "type": p.get("AddressType", ""),
                                     "connected": int(bool(p.get("Connected")))},
                                    describe(addr, p), priority=5))
            known[addr] = int(now)
    if len(known) > 1000:                       # bounded memory of strangers
        known = dict(sorted(known.items(), key=lambda kv: kv[1])[-1000:])
    return events, {"known": known, "powered": obs["powered"]}


def run(dry_run: bool = False, state_file: str | None = None, now=None, sense_mod=None, observer=None):
    return run_sense("bluetooth", observer or observe, detect, dry_run=dry_run,
                     state_file=state_file, now=now, sense_mod=sense_mod)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    return finish(*run(dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
