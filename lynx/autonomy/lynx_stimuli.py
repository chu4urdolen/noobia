"""Lynx autonomy stimulus generator (Phase 3 stimulus test, Gwyn, 2026-11-22).

For the stimulus test the real senses are off, so we feed Lynx fake but
realistic sense lines through the exact same pipeline:

- every line is built with ``sense.format_line`` (canonical format),
- every line parses with ``sense.parse_line``,
- every line matches its pattern with ``ranker._pattern_matches`` (the same
  rule the ranker uses); for all patterns except the documented quirk below
  it is the FIRST pattern in file order whose match rule holds,
- the pattern's ``template`` is filled completely
  (``ranker.fill_template(pattern, parsed)[1] is True``).

``ranker.py``, ``sense.py`` and ``patterns-lynx.json`` are copied here
UNCHANGED; do not edit them.

Known quirk of the pattern set (reported, not fixed here): ``touch-tap-single``
has exactly the same match rule as ``touch-tap`` and comes later in file
order, so no touch/tap line can ever match it first. It is harmless: a tap
line without a ``count`` field makes ``touch-tap``'s template fall back to
exactly the same sentence ("Someone tapped your screen."), so the sentence
Lynx hears is correct whichever of the two wins. ``first_match_id`` and the
tests account for this explicitly.
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import time
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
import os as _os
for _p in (str(Path(_os.environ.get('NOOBIA', '/noobia')) / 'common' / 'autonomy'), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _ensure_viewlog() -> None:
    """sense.py imports viewlog at module load; provide a harmless stub if the
    real one (common/autonomy/viewlog.py) is not importable. We only import
    sense/ranker for parsing and rendering, never emit through it."""
    try:
        import viewlog  # noqa: F401
    except Exception:
        stub = types.ModuleType("viewlog")

        def write(*_args, **_kwargs):
            return False

        stub.write = write
        sys.modules["viewlog"] = stub


_ensure_viewlog()

import ranker  # noqa: E402
import sense  # noqa: E402

_raw = json.loads((HERE / "patterns-lynx.json").read_text(encoding="utf-8"))
PATTERNS: list[dict] = _raw["store"] if isinstance(_raw, dict) else _raw
PATTERNS_BY_ID: dict[str, dict] = {p["id"]: p for p in PATTERNS}

LABELS = ["person", "cat", "dog", "laptop", "cup", "cell_phone",
          "book", "chair", "tv", "bottle"]
ORIENTATIONS = ["portrait", "landscape", "flat_up"]
POWER_STATES = ["charging", "discharging", "full"]

# pattern ids that are shadowed by an earlier pattern with an identical match
# rule (file order), so "first match" is the shadowing pattern instead.
SHADOWED_BY: dict[str, str] = {
    "touch-tap-single": "touch-tap",
}


def _conf(rng: random.Random) -> str:
    """Confidence in 0.30..0.99 with 2-4 decimals, as a string."""
    d = rng.randint(2, 4)
    return f"{rng.uniform(0.30, 0.99):.{d}f}"


def _other(rng: random.Random, choices: list[str], avoid: str) -> str:
    return rng.choice([c for c in choices if c != avoid])


def _ip(rng: random.Random) -> str:
    return f"192.168.100.{rng.randint(1, 254)}"


def _mac(rng: random.Random) -> str:
    return ":".join(f"{rng.randint(0, 255):02x}" for _ in range(6))


def _camera_objects(rng: random.Random):
    k = rng.randint(1, 5)
    cam = rng.choice(["back", "front"])
    items = "/".join(f"{rng.choice(LABELS)}({_conf(rng)})" for _ in range(k))
    return {"cam": cam, "n": k}, items


def _motion_position(rng: random.Random):
    tilt = rng.randint(0, 90)
    to = "horizontal" if tilt < 45 else "vertical"
    frm = "vertical" if to == "horizontal" else "horizontal"
    return {"to": to, "from": frm, "tilt": tilt}, "position changed"


def _orientation(rng: random.Random, text: str):
    to = rng.choice(ORIENTATIONS)
    return {"to": to, "from": _other(rng, ORIENTATIONS, to)}, text


def _thermal_change(rng: random.Random):
    delta = rng.randint(5, 15)
    direction = rng.choice(["rose", "dropped"])
    c = rng.randint(25, 55)
    prev = c - delta if direction == "rose" else c + delta
    text = "warmer" if direction == "rose" else "cooler"
    return {"dir": direction, "c": c, "delta": delta, "prev": prev}, text


def _power_change(rng: random.Random):
    to = rng.choice(POWER_STATES)
    return {"from": _other(rng, POWER_STATES, to), "to": to}, "power source changed"


_VALUES = {
    "touch-tap": lambda rng: (
        {"count": rng.randint(1, 9), "dur_ms": rng.randint(40, 300)},
        "taps on the panel"),
    "touch-tap-single": lambda rng: (
        {"dur_ms": rng.randint(40, 150)},
        "a tap on the panel"),
    "touch-hold": lambda rng: (
        {"dur_ms": rng.randint(1500, 6000)},
        "a hold on the panel"),
    "camera-objects": _camera_objects,
    "camera-object": lambda rng: (
        {"label": rng.choice(LABELS), "conf": _conf(rng)},
        "an object"),
    "motion-position": _motion_position,
    "motion-pickup": lambda rng: _orientation(rng, "picked up"),
    "motion-placed": lambda rng: _orientation(rng, "placed down"),
    "thermal-change": _thermal_change,
    "thermal-hot": lambda rng: (
        {"soc_mc": rng.randint(45, 55) * 1000 + rng.randint(0, 999),
         "state": rng.choice(["charging", "discharging"])},
        "warm"),
    "power-charging": _power_change,
    "battery-low": lambda rng: (
        {"cap": rng.randint(5, 19), "state": "discharging"}, "low"),
    "battery-critical": lambda rng: (
        {"cap": rng.randint(1, 4), "state": "discharging"}, "critical"),
    "hearing-sound": lambda rng: (
        {"peak": rng.randint(30, 400), "rms": f"{rng.uniform(2.0, 30.0):.2f}"},
        "heard sound"),
    "light-bright": lambda rng: (
        {"raw": rng.randint(400, 999)}, "bright"),
    "light-dark": lambda rng: (
        {"raw": rng.randint(0, 100)}, "dark"),
    "proximity-near": lambda rng: (
        {"dist": rng.randint(0, 1)}, "near"),
    "proximity-far": lambda rng: (
        {"dist": rng.randint(3, 12)}, "far"),
    "network-device-seen": lambda rng: (
        {"ip": _ip(rng), "mac": _mac(rng)}, "seen"),
    "network-device-lost": lambda rng: (
        {"ip": _ip(rng)}, "lost"),
    "wifi-down": lambda rng: ({"iface": "wlan0"}, "Wi-Fi went down"),
    "wifi-up": lambda rng: ({"iface": "wlan0"}, "Wi-Fi is back"),
    "wifi-weak": lambda rng: (
        {"signal": rng.randint(-95, -60), "iface": "wlan0"}, "weak"),
    "nexus-up": lambda rng: (
        {"host": "192.168.100.106", "port": 112}, "back"),
    "nexus-down": lambda rng: (
        {"host": "192.168.100.106", "port": 112, "errors": rng.randint(1, 5)},
        "gone"),
}


def first_match_id(parsed: dict) -> str | None:
    """First pattern id in file order whose match rule holds for this line.

    Uses the exact matching rule of ranker.process (_pattern_matches)."""
    for p in PATTERNS:
        if ranker._pattern_matches(p, parsed):
            return p["id"]
    return None


def generate(pattern_id: str, rng: random.Random) -> str:
    """One realistic, randomized sense line for the given pattern id.

    Canonical via sense.format_line; parseable, matching the pattern, and
    filling its template completely (see module docstring for the
    touch-tap-single shadowing quirk)."""
    pat = PATTERNS_BY_ID[pattern_id]
    fields, text = _VALUES[pattern_id](rng)
    return sense.format_line(
        1, pat["match"]["sense"], pat["match"]["event"], fields=fields, text=text
    )


def schedule(rng: random.Random, n: int,
             min_s: float, max_s: float) -> list[tuple[float, str, str]]:
    """Random sequence of n stimuli as (delay_s, pattern_id, line).

    Covers every pattern id at least once when n >= number of patterns;
    delays are uniformly random in [min_s, max_s]."""
    if n < 0:
        raise ValueError("n must be >= 0")
    if max_s < min_s:
        raise ValueError("max_s must be >= min_s")
    ids = [p["id"] for p in PATTERNS]
    if n >= len(ids):
        seq = list(ids)
        rng.shuffle(seq)
        seq.extend(rng.choice(ids) for _ in range(n - len(ids)))
        rng.shuffle(seq)
    else:
        seq = [rng.choice(ids) for _ in range(n)]
    return [(round(rng.uniform(min_s, max_s), 2), pid, generate(pid, rng))
            for pid in seq]


DEFAULT_CMD = "logger -t noobia-sense -p user.notice"


def _emit(cmd: str, line: str) -> str | None:
    """Run the emit command with the line as one final argument, no shell,
    5 s timeout. Returns an error string on failure, else None."""
    argv = cmd.split()
    if not argv:
        return "empty emit command"
    try:
        proc = subprocess.run(argv + [line], timeout=5,
                              capture_output=True, check=False)
    except subprocess.TimeoutExpired:
        return f"timeout after 5s: {cmd!r}"
    except OSError as e:
        return f"could not run {cmd!r}: {e}"
    if proc.returncode != 0:
        return f"command exited {proc.returncode}: {cmd!r}"
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Feed Lynx randomized fake sense lines (stimulus test).")
    ap.add_argument("--count", type=int, default=30, help="number of stimuli")
    ap.add_argument("--min-delay", type=float, default=0.5,
                    help="minimum delay between stimuli in seconds")
    ap.add_argument("--max-delay", type=float, default=2.0,
                    help="maximum delay between stimuli in seconds")
    ap.add_argument("--seed", type=int, default=None, help="RNG seed")
    ap.add_argument("--dry-run", action="store_true",
                    help="no sleeping, no emit command; only print JSON lines")
    ap.add_argument("--emit-cmd", default=DEFAULT_CMD,
                    help="command run with the line as final argument")
    args = ap.parse_args(argv)

    if args.count < 0:
        ap.error("--count must be >= 0")
    if args.max_delay < args.min_delay:
        ap.error("--max-delay must be >= --min-delay")

    rng = random.Random(args.seed)
    items = schedule(rng, args.count, args.min_delay, args.max_delay)
    for delay, pattern_id, line in items:
        if not args.dry_run:
            time.sleep(delay)
        pattern = PATTERNS_BY_ID[pattern_id]
        parsed = sense.parse_line(line)
        expected = ranker.render_message(pattern, parsed) if parsed else ""
        record = {
            "t": time.time(),
            "pattern": pattern_id,
            "line": line,
            "expected": expected,
        }
        print(json.dumps(record), flush=True)
        if not args.dry_run:
            err = _emit(args.emit_cmd, line)
            if err is not None:
                print(json.dumps({"error": err, "cmd": args.emit_cmd,
                                  "pattern": pattern_id}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
