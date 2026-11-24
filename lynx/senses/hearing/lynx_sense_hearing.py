#!/usr/bin/env python3
"""S9 hearing sense for Lynx: acoustic level sampling.

Sampled sense. Data source: ``/usr/local/share/lynx/agent-tools/lynx_microphone_level.sh``
or ``/usr/local/bin/lynx-mic-level``.
Expects JSON stdin ({}) and returns:
{"captured": true, "late_rms": float, "late_peak": int, ...}

Events:
- peak >= 100 or rms >= 30.0 -> NOOBIA P3 hearing sound.heard peak=... rms=...
  (only when Nexus hearing is unavailable; otherwise the clip below says more)
- every 15 samples: NOOBIA P0 hearing status.sample peak=... rms=...

Listening (G1/G2, Gwyn 2026-11-24): when a level sample is loud, a background
thread records a LISTEN_S clip (lynx-microphone-clip: PCM only in memory) and
posts it to nexus_hear (AST sound classes + Whisper). The clip is dropped
right after. Lines:
- hearing.speech lang=..  | the words           ("Tom said ...")
- hearing.sound          | knock               (top non-speech AudioSet class)
- hearing.startle rms=.. ratio=..               (sudden level far above the room)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from lynx_senses_lib import (  # noqa: E402
    SenseUnavailable,
    base_result,
    emit_line,
    failure,
    finish,
    import_sense,
    load_state,
    now_ts,
    save_state,
    state_path,
)

DEFAULT_MIC_BIN = "/usr/local/share/lynx/agent-tools/lynx_microphone_level.sh"
DEFAULT_ENABLED_FILE = "/var/lib/noobia/senses/hearing/enabled"
NEXUS_HEARING_URL = "http://192.168.100.106:112/api/v1/hearing"
HEARING_PEAK_THRESHOLD = 80
CLIP_BIN = os.environ.get("LYNX_MIC_CLIP_BIN", "/usr/local/bin/lynx_microphone_clip.py")
HEAR_URL = os.environ.get("NOOBIA_HEAR_URL", "http://192.168.100.106:5052/hear?rate=48000")
LISTEN_S = 4
LISTEN_COOLDOWN_S = 2.0       # between clips
HEAR_TIMEOUT_S = 40
SOUND_MIN_SCORE = 0.3
SOUND_REPEAT_S = 120          # the same sound label again only after this
STARTLE_RATIO = 8.0           # rms this many times the quiet room ...
STARTLE_MIN_RMS = 400.0       # ... and at least this loud
STARTLE_COOLDOWN_S = 30
QUIET_SOUNDS = {"speech", "silence", "inside, small room", "inside, large room or hall",
                "white noise", "static", "hum", "noise", "pink noise",
                "male speech, man speaking", "female speech, woman speaking",
                "conversation", "narration, monologue"}

_listen = {"thread": None, "last_end": 0.0, "last_sound": {}}
HEARING_RMS_THRESHOLD = 25.0
HEARING_SAMPLE_EVERY = 15


def is_hearing_enabled(enabled_file: str | Path = DEFAULT_ENABLED_FILE,
                       nexus_url: str = NEXUS_HEARING_URL) -> bool:
    # 1. Local file override if present
    p = Path(enabled_file)
    if p.exists():
        try:
            val = p.read_text().strip().lower()
            return val in ("1", "true", "on", "yes")
        except OSError:
            pass

    # 2. Check Nexus toggle over LAN
    try:
        import urllib.request
        req = urllib.request.Request(nexus_url, headers={"User-Agent": "LynxSense/1.0"})
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                return bool(data.get("enabled", False))
    except Exception:
        pass

    # 3. Disabled by default
    return False


def read_microphone_level(bin_path: str = DEFAULT_MIC_BIN) -> dict:
    cmd = os.environ.get("LYNX_MIC_BIN", bin_path)
    res = subprocess.run([cmd], input=b"{}\n", capture_output=True, timeout=8, check=True)
    return json.loads(res.stdout)


def record_clip(seconds: int = LISTEN_S) -> bytes:
    """Raw S16LE 48 kHz mono PCM in memory, from the clip tool's stdout."""
    res = subprocess.run(["/usr/bin/python3", CLIP_BIN, str(seconds)], capture_output=True,
                         timeout=seconds + 10)
    if res.returncode != 0 or not res.stdout:
        raise RuntimeError((res.stderr or b"clip failed").decode("utf-8", "replace")[-160:])
    return res.stdout


def ask_nexus(pcm: bytes, url: str = HEAR_URL) -> dict:
    import urllib.request
    req = urllib.request.Request(url, data=pcm, method="POST",
                                 headers={"Content-Type": "application/octet-stream"})
    with urllib.request.urlopen(req, timeout=HEAR_TIMEOUT_S) as r:
        return json.loads(r.read())


def heard_lines(sense, answer: dict, now: float, dry_run: bool) -> list[str]:
    """Sense lines for one nexus_hear answer (speech first, else a notable sound)."""
    lines = []
    speech = " ".join(str(answer.get("speech") or "").split())[:200]
    if speech:
        lines.append(emit_line(sense, 1, "hearing", "speech",
                               fields={"lang": answer.get("language") or "unknown"},
                               text=speech, dry_run=dry_run))
        return lines
    for snd in answer.get("sounds") or []:
        label = str(snd.get("label", "")).strip()
        if not label or label.lower() in QUIET_SOUNDS or float(snd.get("score", 0)) < SOUND_MIN_SCORE:
            continue
        key = label.lower()
        if now - _listen["last_sound"].get(key, -1e12) < SOUND_REPEAT_S:
            break
        _listen["last_sound"][key] = now
        lines.append(emit_line(sense, 1, "hearing", "sound",
                               fields={"score": round(float(snd["score"]), 2)},
                               text=label.lower()[:60], dry_run=dry_run))
        break
    return lines


def _listen_worker(sense, dry_run: bool, recorder, asker, enabled_check=None) -> None:
    try:
        # Tom 2026-11-24: record only while hearing is on - re-checked at the
        # last moment, so switching it off also stops a clip about to start.
        if not (enabled_check or is_hearing_enabled)():
            _listen["error"] = None
            return
        pcm = recorder()
        try:
            answer = asker(pcm)
        finally:
            del pcm                      # the clip never outlives this request
        heard_lines(sense, answer, now_ts(), dry_run)
        _listen["error"] = None
        _listen["ok"] = True
    except Exception as exc:  # noqa: BLE001 - listening is best effort
        _listen["error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
        _listen["ok"] = False
    finally:
        _listen["last_end"] = now_ts()


def start_listening(sense, dry_run: bool = False, recorder=None, asker=None, now=None,
                    background: bool = True) -> bool:
    """Start one clip+hear in the background unless one is running or too soon."""
    import threading
    t = now if now is not None else now_ts()
    th = _listen.get("thread")
    if th is not None and th.is_alive():
        return False
    if t - _listen.get("last_end", 0.0) < LISTEN_COOLDOWN_S:
        return False
    args = (sense, dry_run, recorder or record_clip, asker or ask_nexus,
            (lambda: True) if recorder is not None else None)   # tests inject a recorder
    if not background:
        _listen_worker(*args)
        return True
    th = threading.Thread(target=_listen_worker, args=args, name="lynx-listen", daemon=True)
    _listen["thread"] = th
    th.start()
    return True


def listening() -> bool:
    th = _listen.get("thread")
    return th is not None and th.is_alive()


def run(dry_run: bool = False, state_file: str | None = None,
        reader=None, now: int | None = None,
        enabled: bool | None = None, recorder=None, asker=None,
        listen_enabled: bool = True) -> tuple[dict, int]:
    t = int(now if now is not None else now_ts())
    # Disabled by default
    is_on = is_hearing_enabled() if enabled is None else enabled
    if not is_on:
        return base_result("hearing", enabled=False, emitted=[], dry_run=dry_run), 0

    try:
        sense = import_sense()
    except SenseUnavailable as exc:
        return failure("hearing", exc)

    if listening():
        # The clip holds the microphone; the level sample waits its turn.
        return base_result("hearing", emitted=[], dry_run=dry_run, detail="listening"), 0

    try:
        data = (reader or read_microphone_level)()
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return failure("hearing", exc)

    if not data.get("captured"):
        return failure("hearing", RuntimeError(data.get("error", "capture failed")))

    peak = int(data.get("late_peak", 0))
    rms = float(data.get("late_rms", 0.0))

    path = state_path("hearing", state_file)
    state = load_state(path)
    emitted: list[str] = []
    samples = int(state.get("samples", 0)) + 1
    prev_heard = state.get("sound_heard", False)

    sound_heard = peak >= HEARING_PEAK_THRESHOLD or rms >= HEARING_RMS_THRESHOLD

    quiet = float(state.get("quiet_rms", rms if rms > 0 else 5.0))
    if not sound_heard:
        quiet = 0.9 * quiet + 0.1 * rms          # the room's usual level
    ratio = rms / max(quiet, 1.0)
    if (samples > 3 and rms >= STARTLE_MIN_RMS and ratio >= STARTLE_RATIO
            and t - float(state.get("startle_t") or -1e12) >= STARTLE_COOLDOWN_S):
        emitted.append(emit_line(sense, 1, "hearing", "startle",
                                 fields={"rms": int(rms), "ratio": int(ratio)},
                                 text="a sudden loud sound", dry_run=dry_run))
        state["startle_t"] = t
    nexus_hearing = listen_enabled and sound_heard and samples > 1
    if nexus_hearing:
        start_listening(sense, dry_run=dry_run, recorder=recorder, asker=asker)

    if samples == 1:
        # First sample sets baseline
        pass
    elif sound_heard and not prev_heard and not (nexus_hearing and _listen.get("ok")):
        # The plain level line only while Nexus hearing has not answered: then
        # the clip's speech/sound line says more, and this one would repeat it.
        line = emit_line(
            sense,
            1,
            "hearing",
            "sound.heard",
            fields={"peak": peak, "rms": round(rms, 1)},
            text=f"Lynx heard sound (peak={peak}, rms={round(rms, 1)})",
            dry_run=dry_run,
        )
        emitted.append(line)

    if samples % HEARING_SAMPLE_EVERY == 0:
        line = emit_line(
            sense,
            0,
            "hearing",
            "status.sample",
            fields={"peak": peak, "rms": round(rms, 1)},
            text=f"Hearing sample peak={peak} rms={round(rms, 1)}",
            dry_run=dry_run,
        )
        emitted.append(line)

    new_state = {
        "samples": samples,
        "sound_heard": sound_heard,
        "last_peak": peak,
        "last_rms": rms,
        "last_ts": t,
        "quiet_rms": round(quiet, 2),
        "startle_t": state.get("startle_t"),
    }
    if not dry_run:
        save_state(path, new_state)

    result = base_result("hearing", emitted=emitted, dry_run=dry_run)
    result.update({
        "peak": peak,
        "rms": round(rms, 1),
        "sound_heard": sound_heard,
        "samples": samples,
        "listening": listening(),
        "listen_error": _listen.get("error"),
    })
    return result, 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    res, code = run(dry_run=args.dry_run)
    return finish(res, code)


if __name__ == "__main__":
    main()
