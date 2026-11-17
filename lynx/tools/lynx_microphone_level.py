#!/usr/bin/env python3
"""One-second Lynx microphone level sample; never retain or transmit PCM."""

import array
import fcntl
import json
import math
from pathlib import Path
import re
import subprocess

BASELINE = {50: 0, 665: 0, 667: 0, 671: 0, 682: 0, 686: 0, 594: 1, 598: 1}
ROUTE = ((682, 2), (50, 1))
LOCK = Path("/run/lynx/microphone-level.lock")


def run(argv, timeout=3):
    result = subprocess.run(argv, capture_output=True, timeout=timeout, check=False)
    if result.returncode:
        raise RuntimeError(argv[0] + " failed")
    return result.stdout


def value(numid):
    output = run(["amixer", "-c0", "cget", f"numid={numid}"])
    found = re.search(rb": values=(on|off|[0-9]+)\s*$", output)
    if not found:
        raise RuntimeError(f"unexpected mixer value for {numid}")
    raw = found.group(1)
    return 1 if raw == b"on" else 0 if raw == b"off" else int(raw)


def set_value(numid, number):
    run(["amixer", "-c0", "cset", f"numid={numid}", str(number)])
    if value(numid) != number:
        raise RuntimeError(f"mixer control {numid} did not reach expected value")


def guarded_health():
    health = json.loads(run(["/usr/local/bin/lynx-status", "--assert-ready"], 5))
    if (health["issues"] or health["battery"]["capacity_percent"] < 25 or
        health["battery"]["temperature_mC"] >= 35000 or
        health["thermal"]["max_mC"] >= 45000):
        raise RuntimeError("battery, thermal, or Alpine health guard failed")
    return health["boot_id"]


def sample_level():
    boot_id = guarded_health()
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("microphone sample already running") from exc
        actual = {numid: value(numid) for numid in BASELINE}
        if actual != BASELINE:
            raise RuntimeError("mixer baseline changed; capture refused")
        changed = []
        try:
            for numid, selected in ROUTE:
                changed.append(numid)
                set_value(numid, selected)
            data = run(["arecord", "-D", "hw:0,11", "-f", "S16_LE",
                        "-r", "48000", "-c", "1", "--period-size=1024",
                        "--buffer-size=4096", "-d", "1", "-t", "raw", "-"], 4)
        finally:
            failures = []
            for numid in reversed(changed):
                try:
                    set_value(numid, actual[numid])
                except Exception:
                    failures.append(numid)
            if failures or value(594) != 1 or value(598) != 1:
                raise RuntimeError(f"mixer restoration failed: {failures}")
        samples = array.array("h")
        samples.frombytes(data[:len(data) // 2 * 2])
        if not 40000 <= len(samples) <= 50000:
            raise RuntimeError("unexpected microphone sample length")
        window = samples[14400:38400]
        rms = math.sqrt(sum(item * item for item in window) / len(window))
        peak = max(abs(item) for item in window)
        del samples, data
        return {"captured": True, "external_sound_validated": False,
                "duration_ms": 1000, "sample_rate_hz": 48000,
                "late_rms": round(rms, 2), "late_peak": peak,
                "raw_audio_retained": False, "mixer_restored": True,
                "boot_id": boot_id}


def main():
    try:
        print(json.dumps(sample_level(), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"captured": False, "error": str(exc),
                          "raw_audio_retained": False}, sort_keys=True))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
