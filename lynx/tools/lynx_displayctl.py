#!/usr/bin/env python3
"""Local/SSH control for Lynx's portrait and frame-by-frame animations."""

import argparse
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys


ROOT = Path("/var/lib/lynx-display")
FRAMES = ROOT / "frames"
MANIFEST = FRAMES / "manifest.json"
SELECTION = ROOT / "selection"
NAME = re.compile(r"[a-z0-9_]{1,63}\Z")
PIXELS = 1240 * 2772 * 2


def valid(name):
    if not NAME.fullmatch(name):
        raise ValueError("names must contain only lowercase letters, digits, and underscores")
    return name


def atomic_text(path, content):
    temp = path.with_name(path.name + ".new")
    if temp.exists():
        raise ValueError(f"stale temporary file: {temp}")
    with temp.open("x") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def load():
    manifest = json.loads(MANIFEST.read_text())
    if (manifest.get("width"), manifest.get("height")) != (1240, 2772):
        raise ValueError("unexpected frame dimensions")
    return manifest


def names(manifest):
    return {entry["name"] for entry in manifest["frames"]}


def check_frame(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("frame must be a regular gzip file of at most 8 MiB")
    count = 0
    with gzip.open(path, "rb") as stream:
        while True:
            chunk = stream.read(min(65536, PIXELS + 1 - count))
            if not chunk:
                break
            count += len(chunk)
            if count > PIXELS:
                raise ValueError("frame exceeds display dimensions")
    if count != PIXELS:
        raise ValueError("frame size does not match 1240×2772 RGB565")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    sub.add_parser("status")
    pose = sub.add_parser("pose")
    pose.add_argument("name")
    animation = sub.add_parser("animate")
    animation.add_argument("name")
    register = sub.add_parser("register")
    register.add_argument("name")
    register.add_argument("source", type=Path)
    define = sub.add_parser("define-animation")
    define.add_argument("name")
    define.add_argument("frames", nargs="+")
    args = parser.parse_args()
    ROOT.mkdir(mode=0o700, exist_ok=True)
    with (ROOT / "control.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        manifest = load()
        available = names(manifest)
        if args.command == "list":
            print(json.dumps({"poses": sorted(available),
                "animations": manifest["animations"]}, indent=2))
        elif args.command == "status":
            selection = SELECTION.read_text().strip() if SELECTION.exists() else "pose 01_standing_smile"
            pidfile = Path("/run/lynx/display-auto.pid")
            print(json.dumps({"selection": selection, "renderer_pid":
                pidfile.read_text().strip() if pidfile.exists() else None}))
        elif args.command == "pose":
            name = valid(args.name)
            if name not in available or not (FRAMES / f"{name}.rgb565.gz").is_file():
                raise ValueError("unknown pose")
            atomic_text(SELECTION, f"pose {name}\n")
            print(f"pose {name}")
        elif args.command == "animate":
            name = valid(args.name)
            animation = manifest["animations"].get(name)
            if not animation or any(frame not in available for frame in animation["frames"]):
                raise ValueError("unknown or incomplete animation")
            if not (FRAMES / f"{name}.list").is_file():
                raise ValueError("animation list missing")
            atomic_text(SELECTION, f"animate {name}\n")
            print(f"animate {name} at 500 ms/frame")
        elif args.command == "register":
            name = valid(args.name)
            if name in available or "180deg" in name:
                raise ValueError("pose already exists or excluded corrupted angle")
            check_frame(args.source)
            target = FRAMES / f"{name}.rgb565.gz"
            if target.exists():
                raise ValueError("destination frame already exists")
            with args.source.open("rb") as src, target.open("xb") as dst:
                shutil.copyfileobj(src, dst)
                dst.flush()
                os.fsync(dst.fileno())
            target.chmod(0o600)
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            manifest["frames"].append({"name": name, "file": target.name,
                                       "sha256": digest, "bytes": target.stat().st_size})
            atomic_text(MANIFEST, json.dumps(manifest, indent=2) + "\n")
            print(f"registered {name}")
        elif args.command == "define-animation":
            name = valid(args.name)
            if name in manifest["animations"]:
                raise ValueError("animation already exists")
            frames = [valid(frame) for frame in args.frames]
            if not 2 <= len(frames) <= 64 or any(frame not in available for frame in frames):
                raise ValueError("animation needs 2–64 registered poses")
            path = FRAMES / f"{name}.list"
            if path.exists():
                raise ValueError("animation list already exists")
            atomic_text(path, "\n".join(frames) + "\n")
            manifest["animations"][name] = {"frames": frames, "frame_duration_ms": 500}
            atomic_text(MANIFEST, json.dumps(manifest, indent=2) + "\n")
            print(f"defined animation {name}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"lynx-displayctl: {exc}", file=sys.stderr)
        raise SystemExit(1)
