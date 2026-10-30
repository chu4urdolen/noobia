#!/usr/bin/env python3
"""Lynx media controller. Local Unix socket; SSH is the remote transport."""

import argparse
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import time
import wave

ROOT = Path("/var/lib/lynx-media")
SOCK = Path("/run/lynx/media.sock")
CATALOG = ROOT / "catalog.json"
STATE = ROOT / "state.json"
DISPLAY = Path("/var/lib/lynx-display")
NAME = re.compile(r"[a-z0-9_]{1,63}\Z")
MIXER = [
    ("I2S3_CH1 DL1_CH1", "on"),
    ("I2S3_CH2 DL1_CH2", "on"),
    ("I2S3_HD_Mux", "Low_Jitter"),
    ("primary_play_scenario", "on"),
    ("Audio IRQ1 CNT", "1024"),
    ("TFA_CHIP_SELECTOR", "2"),
    ("TFA98XX Profile", "MMI_Test_SpeakerR"),
]
RESET = [
    ("Speaker_R_Mute_Switch", "On"),
    ("Speaker_L_Mute_Switch", "On"),
    ("I2S3_CH1 DL1_CH1", "off"),
    ("I2S3_CH2 DL1_CH2", "off"),
    ("primary_play_scenario", "off"),
    ("TFA_CHIP_SELECTOR", "0"),
    ("TFA98XX Profile", "StereoR"),
    ("I2S3_HD_Mux", "Normal"),
    ("Audio IRQ1 CNT", "0"),
]


def name(value):
    if not isinstance(value, str) or not NAME.fullmatch(value):
        raise ValueError("invalid media name")
    return value


def save_json(path, value):
    temp = path.with_suffix(".new")
    with temp.open("w") as f:
        json.dump(value, f, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)


def mixer(control, value):
    subprocess.run(["amixer", "-c0", "cset", f"name={control}", value],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                   timeout=4)


def mute():
    for control, value in RESET:
        try:
            mixer(control, value)
        except (OSError, subprocess.SubprocessError):
            pass


def wav_info(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 3_000_000:
        raise ValueError("sound must be a regular WAV below 3 MB")
    with wave.open(str(path), "rb") as w:
        if (w.getnchannels(), w.getsampwidth(), w.getframerate()) != (2, 2, 48000):
            raise ValueError("sound must be stereo 16-bit 48 kHz WAV")
        if not 0 < w.getnframes() <= 48_000 * 30:
            raise ValueError("sound must be at most 30 seconds")
        # The amplifier path has no proven software volume control yet.
        import array
        while True:
            chunk = w.readframes(4096)
            if not chunk:
                break
            samples = array.array("h")
            samples.frombytes(chunk)
            if max(abs(x) for x in samples) > 3276:
                raise ValueError("sound exceeds 10% digital peak")


class Controller:
    def __init__(self):
        ROOT.mkdir(mode=0o700, exist_ok=True)
        old = json.loads(STATE.read_text()) if STATE.exists() else {}
        self.channels = {}
        for kind in ("sound", "image"):
            saved = old.get(kind, {})
            self.channels[kind] = dict(current=None, queue=saved.get("queue", [])[:64],
                                       history=saved.get("history", [])[-64:],
                                       mode="stopped", remaining=None, started=None)
        self.proc = None
        self.errors = []
        self.save()

    def available(self, kind):
        if kind == "sound":
            return json.loads(CATALOG.read_text())["sounds"]
        if kind == "image":
            manifest = json.loads((DISPLAY / "frames/manifest.json").read_text())
            return {**{x["name"]: {"type": "pose"} for x in manifest["frames"]},
                    **{k: {"type": "animation", **v}
                       for k, v in manifest["animations"].items()}}
        raise ValueError("kind must be sound or image")

    def validate(self, kind, item):
        item = name(item)
        entry = self.available(kind).get(item)
        if not entry:
            raise ValueError("unknown media item")
        if kind == "sound":
            file = name(entry["file"].removesuffix(".wav")) + ".wav"
            path = ROOT / "sounds" / file
            wav_info(path)
        return entry

    def save(self):
        save_json(STATE, {kind: {"queue": s["queue"], "history": s["history"]}
                          for kind, s in self.channels.items()})

    def image_duration(self, entry):
        if entry["type"] == "animation":
            return len(entry["frames"]) * entry.get("frame_duration_ms", 500) / 1000
        return 5.0

    def show_image(self, item):
        entry = self.validate("image", item)
        selection = ("animate " if entry["type"] == "animation" else "pose ") + item + "\n"
        path = DISPLAY / "selection"
        temp = DISPLAY / "selection.media.new"
        temp.write_text(selection)
        os.replace(temp, path)
        return self.image_duration(entry)

    def freeze_image(self):
        s = self.channels["image"]
        if s["mode"] != "playing" or s["started"] is None or not s["current"]:
            return
        entry = self.validate("image", s["current"])
        if entry["type"] != "animation":
            return
        elapsed = max(0, time.monotonic() - s["started"])
        step = entry.get("frame_duration_ms", 500) / 1000
        frame = entry["frames"][min(int(elapsed / step), len(entry["frames"]) - 1)]
        temp = DISPLAY / "selection.media.new"
        temp.write_text(f"pose {frame}\n")
        os.replace(temp, DISPLAY / "selection")

    def stop_current(self, kind):
        s = self.channels[kind]
        if kind == "sound":
            if self.proc and self.proc.poll() is None:
                self.proc.send_signal(signal.SIGCONT)
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                    self.proc.wait(timeout=2)
            self.proc = None
            mute()
        else:
            self.freeze_image()
        s["mode"] = "stopped"
        s["started"] = None
        s["remaining"] = None

    def start(self, kind, item, remember=True):
        entry = self.validate(kind, item)
        s = self.channels[kind]
        self.stop_current(kind)
        if remember and s["current"]:
            s["history"].append(s["current"])
            s["history"] = s["history"][-64:]
        s["current"] = None
        if kind == "sound":
            if "mt6983mt6338" not in Path("/proc/asound/cards").read_text():
                raise RuntimeError("sound card unavailable; audio modules are not loaded")
            if not Path("/lib/firmware/tfa98xx.cnt").is_file():
                raise RuntimeError("speaker firmware unavailable")
            firmware = subprocess.run(
                ["amixer", "-c0", "cget", "name=TFA98XX Firmware"],
                check=True, capture_output=True, text=True, timeout=4)
            if ": values=1" not in firmware.stdout:
                raise RuntimeError("speaker firmware is not loaded")
            try:
                for control, value in MIXER:
                    mixer(control, value)
                mixer("Speaker_R_Mute_Switch", "Off")
                self.proc = subprocess.Popen(
                    ["aplay", "-D", "hw:0,0", "--period-size=1024",
                     "--buffer-size=4096", str(ROOT / "sounds" / entry["file"])],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, start_new_session=True)
            except Exception:
                mute()
                raise
            duration = None
        else:
            duration = self.show_image(item)
        s.update(current=item, mode="playing", started=time.monotonic(),
                 remaining=duration)
        self.save()

    def tick(self):
        s = self.channels["sound"]
        if self.proc and self.proc.poll() is not None:
            if self.proc.returncode:
                self.errors.append(f"aplay exited {self.proc.returncode}")
            self.proc = None
            mute()
            if s["current"]:
                s["history"].append(s["current"])
                s["history"] = s["history"][-64:]
            s.update(current=None, mode="stopped", started=None)
            try:
                self.advance("sound")
            except Exception as exc:
                self.errors.append(str(exc))
        s = self.channels["image"]
        if s["mode"] == "playing" and s["remaining"] is not None:
            if time.monotonic() - s["started"] >= s["remaining"]:
                if s["queue"]:
                    try:
                        self.advance("image")
                    except Exception as exc:
                        self.errors.append(str(exc))
                        s["mode"] = "stopped"
                else:
                    self.freeze_image()
                    s["mode"] = "stopped"
                    s["remaining"] = None
                    s["started"] = None

    def advance(self, kind):
        s = self.channels[kind]
        if s["queue"]:
            item = s["queue"].pop(0)
            try:
                self.start(kind, item)
            except Exception:
                s["queue"].insert(0, item)
                self.save()
                raise
        else:
            if s["current"]:
                s["history"].append(s["current"])
                s["history"] = s["history"][-64:]
            self.stop_current(kind)
            s["current"] = None
            self.save()

    def command(self, req):
        action = req.get("action")
        kind = req.get("kind")
        if action == "catalog":
            return {"sounds": self.available("sound"),
                    "images": self.available("image")}
        if action == "status":
            return {"channels": self.channels, "errors": self.errors[-10:]}
        if kind not in ("sound", "image"):
            raise ValueError("kind must be sound or image")
        s = self.channels[kind]
        if action in ("play", "queue"):
            item = name(req.get("item"))
            self.validate(kind, item)
            if action == "queue":
                if len(s["queue"]) >= 64:
                    raise ValueError("queue full")
                s["queue"].append(item)
                self.save()
                if s["mode"] == "stopped":
                    self.advance(kind)
            else:
                self.start(kind, item)
        elif action == "pause":
            if s["mode"] != "playing":
                raise ValueError("nothing playing")
            if kind == "sound":
                os.kill(self.proc.pid, signal.SIGSTOP)
            else:
                s["remaining"] -= time.monotonic() - s["started"]
                self.freeze_image()
            s["mode"] = "paused"
        elif action == "resume":
            if s["mode"] != "paused":
                raise ValueError("nothing paused")
            if kind == "sound":
                os.kill(self.proc.pid, signal.SIGCONT)
            else:
                self.show_image(s["current"])
            s["mode"] = "playing"
            s["started"] = time.monotonic()
        elif action == "stop":
            self.stop_current(kind)
            s["current"] = None
            s["queue"].clear()
            self.save()
        elif action == "next":
            self.advance(kind)
        elif action == "previous":
            if not s["history"]:
                raise ValueError("no previous item")
            item = s["history"].pop()
            self.start(kind, item, remember=False)
        elif action == "clear":
            s["queue"].clear()
            self.save()
        else:
            raise ValueError("unknown action")
        return {"channel": s}


def serve():
    controller = Controller()
    def shutdown(_signal, _frame):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, shutdown)
    SOCK.parent.mkdir(mode=0o700, exist_ok=True)
    if SOCK.exists():
        raise RuntimeError("socket exists; check for running controller")
    with socket.socket(socket.AF_UNIX) as server:
        server.bind(str(SOCK))
        SOCK.chmod(0o600)
        server.listen(8)
        server.settimeout(0.2)
        try:
            while True:
                controller.tick()
                try:
                    conn, _ = server.accept()
                except socket.timeout:
                    continue
                with conn:
                    conn.settimeout(2)
                    try:
                        req = json.loads(conn.recv(4096))
                        result = {"ok": True, **controller.command(req)}
                    except Exception as exc:
                        result = {"ok": False, "error": str(exc)}
                    conn.sendall((json.dumps(result) + "\n").encode())
        finally:
            controller.stop_current("sound")
            SOCK.unlink(missing_ok=True)


def client(args):
    req = {"action": args.action, "kind": args.kind, "item": args.item}
    with socket.socket(socket.AF_UNIX) as conn:
        conn.settimeout(4)
        conn.connect(str(SOCK))
        conn.sendall(json.dumps(req).encode())
        result = json.loads(conn.recv(65536))
    print(json.dumps(result, indent=2))
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["serve", "catalog", "status", "play",
                                         "pause", "resume", "stop", "queue",
                                         "next", "previous", "clear"])
    parser.add_argument("kind", nargs="?", choices=["sound", "image"])
    parser.add_argument("item", nargs="?")
    options = parser.parse_args()
    if options.action == "serve":
        serve()
    else:
        client(options)
