#!/usr/bin/env python3
"""Lynx senses service loop (installed as the OpenRC service
``lynx-senses``, source: lynx/senses/init/lynx-senses.initd, install is
Aria's IS-2).

Runs the sampled senses on Lynx:

- every 2 s:    touch  (S2) - finger down/up edge -> tap/hold P5
- every 30 s:   wifi   (S3) - link.up/link.down P1, rssi.low P3, P0 sample
- every 30 s:   power  (S4) - battery/thermal/charging events, P0 sample
- every 30 s:   nexus  (S8) - unreachable/reachable P1 transitions

Each sense is one bounded one-shot (its own module, its own state file);
one sense failing never stops the others - the failure is logged as one
line to stderr (the service's error log) with the sense's honest error.
Sense lines go to syslog under the canonical noobia-sense ident via the
shared library. Nothing here writes anywhere else.

Manual single cycle (also the IS-2 verify step):
    python3 /usr/local/lib/noobia/senses/common/lynx_senses_loop.py --once
"""

from __future__ import annotations

import importlib.util
import json
import os
import signal
import sys
import time
from pathlib import Path

SENSES_ROOT = Path(__file__).resolve().parent.parent
TOUCH_EVERY_S = 2.0
FAST_SAMPLE_EVERY_S = 10.0
SAMPLE_EVERY_S = 30.0

_stop = False


def _on_term(signum, frame):
    global _stop
    _stop = True


def load_module(name: str, rel: str):
    path = SENSES_ROOT / rel
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load sense module {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_optional(name: str, rel: str):
    path = SENSES_ROOT / rel
    if path.exists():
        try:
            return load_module(name, rel)
        except Exception as exc:
            print(f"optional sense {name}: {type(exc).__name__}: {str(exc)[:160]}",
                  file=sys.stderr)
    return None


def load_senses():
    senses = {
        "touch": load_module("lynx_sense_touch", "touch/lynx_sense_touch.py"),
        "wifi": load_module("lynx_sense_wifi", "wifi/lynx_sense_wifi.py"),
        "power": load_module("lynx_sense_power", "power/lynx_sense_power.py"),
        "nexus": load_module("lynx_sense_nexus", "nexus/lynx_sense_nexus.py"),
        "light": load_optional("lynx_sense_light", "light/lynx_sense_light.py"),
        "proximity": load_optional("lynx_sense_proximity", "proximity/lynx_sense_proximity.py"),
        "network": load_optional("lynx_sense_network", "network/lynx_sense_network.py"),
        "hearing": load_optional("lynx_sense_hearing", "hearing/lynx_sense_hearing.py"),
        "motion": load_optional("lynx_sense_motion", "motion/lynx_sense_motion.py"),
        "camera": load_optional("lynx_sense_camera", "camera/lynx_sense_camera.py"),
    }
    return senses


def call(name: str, fn) -> dict:
    """Run one sense one-shot; report, never raise."""
    try:
        result, code = fn()
        if not result.get("ok"):
            print(f"sense {name}: {json.dumps(result, sort_keys=True)}",
                  file=sys.stderr)
        return result
    except Exception as exc:  # a sense must never take the loop down
        print(f"sense {name}: {type(exc).__name__}: {str(exc)[:160]}",
              file=sys.stderr)
        return {"ok": False, "sense": name,
                "error": type(exc).__name__}


def one_cycle(*args, **kwargs) -> dict:
    if len(args) == 1 and isinstance(args[0], dict):
        senses = args[0]
    else:
        # Positional signature: touch, wifi, power, nexus, [camera]
        keys = ("touch", "wifi", "power", "nexus", "camera")
        senses = {keys[i]: a for i, a in enumerate(args) if i < len(keys)}
        for k, v in kwargs.items():
            senses[k] = v
    results = {}
    for name, mod in senses.items():
        if mod is not None:
            results[name] = call(name, mod.run)
    return results


def run_loop(*args, **kwargs) -> int:
    signal.signal(signal.SIGTERM, _on_term)
    if len(args) == 1 and isinstance(args[0], dict):
        senses = args[0]
    else:
        keys = ("touch", "wifi", "power", "nexus", "camera")
        senses = {keys[i]: a for i, a in enumerate(args) if i < len(keys)}
        for k, v in kwargs.items():
            senses[k] = v
    last_touch = 0.0
    last_fast = 0.0
    last_sample = 0.0
    while not _stop:
        now = time.monotonic()
        if now - last_touch >= TOUCH_EVERY_S:
            if senses.get("touch"):
                call("touch", senses["touch"].run)
            last_touch = now
        if now - last_fast >= FAST_SAMPLE_EVERY_S:
            for name in ("light", "proximity", "hearing", "motion"):
                if senses.get(name):
                    call(name, senses[name].run)
            last_fast = now
        if now - last_sample >= SAMPLE_EVERY_S:
            for name in ("wifi", "power", "nexus", "network", "camera"):
                if senses.get(name):
                    call(name, senses[name].run)
            last_sample = now
        time.sleep(0.5)
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    senses = load_senses()
    if "--once" in argv:
        summary = one_cycle(senses)
        print(json.dumps({"ok": all(r.get("ok") for r in summary.values()),
                          "results": summary}, sort_keys=True))
        return 0
    return run_loop(senses)


if __name__ == "__main__":
    sys.exit(main())
