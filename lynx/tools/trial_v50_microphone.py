#!/usr/bin/env python3
"""One-second, in-memory Lynx microphone route trial with mixer restoration."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
BOOT = "6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59"

REMOTE = r'''import array, json, math, re, signal, subprocess, sys, time
from pathlib import Path

def interrupted(signum, frame):
    raise InterruptedError("trial interrupted")

for sig in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
    signal.signal(sig, interrupted)

def run(argv, timeout=3):
    return subprocess.run(argv, capture_output=True, timeout=timeout, check=False)

def value(numid):
    result = run(["amixer", "-c0", "cget", "numid=" + str(numid)])
    if result.returncode:
        raise RuntimeError("cget failed for " + str(numid))
    found = re.search(rb": values=(on|off|[0-9]+)\s*$", result.stdout)
    if not found:
        raise RuntimeError("unexpected control value for " + str(numid))
    raw = found.group(1)
    return 1 if raw == b"on" else 0 if raw == b"off" else int(raw)

def set_value(numid, number):
    result = run(["amixer", "-c0", "cset", "numid=" + str(numid), str(number)])
    if result.returncode or value(numid) != number:
        raise RuntimeError("cset failed for " + str(numid))

report = {"state": "starting", "raw_audio_retained": False,
          "changed_controls": [], "restoration": {}}
saved = {}
haptic = sys.argv[1:] == ["haptic"]
beep = sys.argv[1:] == ["beep"]
led = Path("/sys/class/leds/vibrator")
try:
    # Stock mt6338 DAPM route: UL1_CH1 <- ADDA_UL_CH1 <- ADC_L <- PGA_L <- AIN0.
    expected = {50: 0, 665: 0, 667: 0, 671: 0, 682: 0, 686: 0, 594: 1, 598: 1}
    actual = {numid: value(numid) for numid in expected}
    report["baseline_controls"] = actual
    if actual != expected:
        raise RuntimeError("mixer baseline changed; no trial run")
    # Leave speaker routing and gain untouched. Enable only the input path.
    for numid, selected in ((682, 2), (50, 1)):
        saved[numid] = actual[numid]
        set_value(numid, selected)
        report["changed_controls"].append(numid)
    argv = ["arecord", "-D", "hw:0,11", "-f", "S16_LE", "-r", "48000",
            "-c", "1", "--period-size=1024", "--buffer-size=4096",
            "-d", "1", "-t", "raw", "-"]
    if haptic:
        if not led.joinpath("oplus_duration").is_file() or not led.joinpath("oplus_activate").is_file():
            raise RuntimeError("haptic control unavailable")
        capture = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            time.sleep(0.3)
            if capture.poll() is not None:
                raise RuntimeError("capture exited before haptic pulse")
            led.joinpath("oplus_duration").write_text("80\n")
            led.joinpath("oplus_activate").write_text("1\n")
            time.sleep(0.10)
            stdout, stderr = capture.communicate(timeout=4)
        except BaseException:
            if capture.poll() is None:
                capture.kill()
            capture.communicate(timeout=2)
            raise
        finally:
            led.joinpath("oplus_activate").write_text("0\n")
        captured = type("Capture", (), {"stdout": stdout, "stderr": stderr,
                                         "returncode": capture.returncode})()
    elif beep:
        capture = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            time.sleep(0.2)
            if capture.poll() is not None:
                raise RuntimeError("capture exited before beep")
            played = run(["/usr/local/bin/lynx-media", "play", "sound", "beep"], timeout=3)
            if played.returncode:
                raise RuntimeError("beep request failed")
            stdout, stderr = capture.communicate(timeout=4)
        except BaseException:
            if capture.poll() is None:
                capture.kill()
            capture.communicate(timeout=2)
            raise
        finally:
            stopped = run(["/usr/local/bin/lynx-media", "stop", "sound"], timeout=3)
            report["media_stopped_after"] = stopped.returncode == 0
        captured = type("Capture", (), {"stdout": stdout, "stderr": stderr,
                                         "returncode": capture.returncode})()
    else:
        captured = run(argv, timeout=4)
    samples = array.array("h")
    samples.frombytes(captured.stdout[:len(captured.stdout) // 2 * 2])
    report["capture"] = {
        "exit": captured.returncode, "sample_count": len(samples),
        "peak": max((abs(x) for x in samples), default=0),
        "rms": round(math.sqrt(sum(x*x for x in samples) / len(samples)), 2)
               if samples else 0,
        "stderr": captured.stderr.decode(errors="replace")[:1000],
        "stimulus": "haptic" if haptic else "beep" if beep else "none"}
    if (haptic or beep) and len(samples) >= 40000:
        before = samples[:8000]
        during = samples[14400:38400]
        report["capture"]["before_rms"] = round(math.sqrt(sum(x*x for x in before)/len(before)),2)
        report["capture"]["stimulus_rms"] = round(math.sqrt(sum(x*x for x in during)/len(during)),2)
    if len(samples) >= 40000:
        window = samples[14400:38400]
        cosine = sum(x * math.cos(2 * math.pi * 700 * i / 48000)
                     for i, x in enumerate(window))
        sine = sum(x * math.sin(2 * math.pi * 700 * i / 48000)
                   for i, x in enumerate(window))
        report["capture"]["late_rms"] = round(
            math.sqrt(sum(x*x for x in window) / len(window)), 2)
        report["capture"]["tone700_amplitude"] = round(
            2 * math.hypot(cosine, sine) / len(window), 2)
    del samples, captured
    report["state"] = "captured" if report["capture"]["exit"] == 0 else "capture-rejected"
except Exception as exc:
    report["state"] = "failed"
    report["error"] = str(exc)
finally:
    if haptic:
        try:
            led.joinpath("oplus_activate").write_text("0\n")
            report["haptic_off_after"] = True
        except Exception:
            report["haptic_off_after"] = False
    for numid in reversed(list(saved)):
        try:
            set_value(numid, saved[numid])
            report["restoration"][str(numid)] = True
        except Exception as exc:
            report["restoration"][str(numid)] = str(exc)
    try:
        report["speaker_muted_after"] = value(594) == 1 and value(598) == 1
    except Exception:
        report["speaker_muted_after"] = False
print(json.dumps(report, separators=(",", ":")))
'''


def ssh(command, data=None, timeout=15):
    args = ssh_command("192.168.100.107", command)
    args[-2:-2] = ["-p", "2222"]
    return subprocess.run(args, input=data, capture_output=True, text=True, timeout=timeout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    stimulus = parser.add_mutually_exclusive_group()
    stimulus.add_argument("--haptic", action="store_true",
                          help="add one 80 ms known chassis stimulus during capture")
    stimulus.add_argument("--beep", action="store_true",
                          help="play one existing 500 ms quiet beep during capture")
    args = parser.parse_args()
    receipt = ROOT / "logs" / f"v50-microphone-trial-{time.time_ns()}"
    receipt.mkdir(mode=0o700)
    report = {"state": "preflight", "boot_partition_writes": False,
              "persistent_phone_files": False, "steps": []}

    def step(name, command, data=None, timeout=15):
        result = ssh(command, data, timeout)
        (receipt / f"{name}.stdout").write_text(result.stdout)
        (receipt / f"{name}.stderr").write_text(result.stderr)
        report["steps"].append({"name": name, "exit": result.returncode})
        if result.returncode:
            raise RuntimeError(f"{name} failed")
        return result.stdout.strip()

    try:
        identity = step("identity", "uname -r; sha256sum /dev/sdc39 | cut -c1-64").splitlines()
        if identity != ["5.10.149-android12-9-o-g311738fbb5a8", BOOT]:
            raise RuntimeError("not verified V50")
        health = json.loads(step("health_before", "/usr/local/bin/lynx-status --assert-ready"))
        if health["battery"]["capacity_percent"] < 50 or \
           health["battery"]["temperature_mC"] >= 35000 or \
           health["thermal"]["max_mC"] >= 45000:
            raise RuntimeError("health guard failed")
        report["boot_id"] = health["boot_id"]
        step("preflight", "set -eu; rc-service lynx-audio status; "
             "test -c /dev/snd/pcmC0D11c; command -v arecord; "
             "test -r /proc/asound/pcm")
        if args.haptic:
            step("haptic_idle", "test \"$(cat /sys/class/leds/vibrator/oplus_activate)\" = 0")
        if args.beep:
            media = json.loads(step("media_idle", "/usr/local/bin/lynx-media status sound"))
            sound = media.get("channels", {}).get("sound", {})
            if sound.get("current") is not None or sound.get("queue") or \
               sound.get("mode") != "stopped":
                raise RuntimeError("sound channel busy")
        trial = json.loads(step("trial", "python3 - haptic" if args.haptic else
                                "python3 - beep" if args.beep else "python3 -",
                                REMOTE, timeout=12))
        report["trial"] = trial
        if trial.get("state") == "failed":
            raise RuntimeError("phone microphone trial failed")
        if not trial.get("speaker_muted_after") or \
           any(v is not True for v in trial.get("restoration", {}).values()) or \
           (args.haptic and not trial.get("haptic_off_after")) or \
           (args.beep and not trial.get("media_stopped_after")):
            raise RuntimeError("mixer restoration failed")
        after = json.loads(step("health_after", "/usr/local/bin/lynx-status --assert-ready"))
        if after["boot_id"] != report["boot_id"] or \
           after["thermal"]["max_mC"] >= 45000:
            raise RuntimeError("post-trial health changed")
        step("audio_after", "rc-service lynx-audio status; "
             "amixer -c0 cget numid=594 | grep -q ': values=1'; "
             "amixer -c0 cget numid=598 | grep -q ': values=1'")
        report["state"] = "completed-capture" if trial["state"] == "captured" \
                          else "completed-capture-rejected"
    except Exception as exc:
        report.update(state="failed", error=str(exc))
    (receipt / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "receipt": str(receipt / "result.json"),
                      "capture": report.get("trial", {}).get("capture"),
                      "error": report.get("error")}))
    if report["state"] == "failed":
        sys.exit(1)


if __name__ == "__main__":
    main()
