#!/usr/bin/env python3
"""lynx-microphone-clip: record a short mono clip for nexus_hear (Gwyn, 2026-11-24).

Reuses lynx_microphone_level's proven route, lock and health guard: the same
mixer route is set, the same baseline is required, and the mixer is always
restored. The PCM (S16LE, 48 kHz, mono) goes ONLY to standard output - it is
never written to a file here; the caller sends it to Nexus and drops it.

    lynx-microphone-clip [SECONDS]      (1-10, default 4) -> raw PCM on stdout
On failure: a JSON error on stderr, exit 1, nothing on stdout.
"""
import fcntl
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lynx_microphone_level as mic  # noqa: E402

RATE = 48000


def record(seconds: int) -> bytes:
    mic.guarded_health()
    mic.LOCK.parent.mkdir(parents=True, exist_ok=True)
    with mic.LOCK.open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("microphone busy") from exc
        actual = {numid: mic.value(numid) for numid in mic.BASELINE}
        if actual != mic.BASELINE:
            raise RuntimeError("mixer baseline changed; capture refused")
        changed = []
        try:
            for numid, selected in mic.ROUTE:
                changed.append(numid)
                mic.set_value(numid, selected)
            data = mic.run(["arecord", "-D", "hw:0,11", "-f", "S16_LE", "-r", str(RATE), "-c", "1",
                            "--period-size=1024", "--buffer-size=4096", "-d", str(seconds),
                            "-t", "raw", "-"], seconds + 4)
        finally:
            failures = []
            for numid in reversed(changed):
                try:
                    mic.set_value(numid, actual[numid])
                except Exception:
                    failures.append(numid)
            if failures:
                raise RuntimeError(f"mixer restoration failed: {failures}")
    expected = seconds * RATE * 2
    if not 0.8 * expected <= len(data) <= 1.1 * expected:
        raise RuntimeError(f"unexpected clip length {len(data)} for {seconds} s")
    return data


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        seconds = int(argv[0]) if argv else 4
        if not 1 <= seconds <= 10:
            raise ValueError("seconds must be 1..10")
        data = record(seconds)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(json.dumps({"captured": False, "error": str(exc)}) + "\n")
        return 1
    sys.stdout.buffer.write(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
