#!/usr/bin/env python3
"""Bounded local agent bridge to Lynx's established media controller."""

import argparse
import json
import re
import subprocess
import sys

NAME = re.compile(r"[a-z0-9_]{1,63}\Z")
ACTIONS = ("catalog", "status", "play", "stop")
MEDIA = "/usr/local/bin/lynx-media"
HEALTH = "/usr/local/bin/lynx-status"


def arguments(action, request):
    if not isinstance(request, dict):
        raise ValueError("JSON object required")
    if action in ("catalog", "status"):
        if request:
            raise ValueError("no arguments accepted")
        return [MEDIA, action]
    if action == "stop":
        if set(request) != {"kind"} or request["kind"] not in ("sound", "image"):
            raise ValueError("kind must be sound or image")
        return [MEDIA, action, request["kind"]]
    if (set(request) != {"kind", "item"} or request["kind"] not in ("sound", "image") or
            not isinstance(request["item"], str) or not NAME.fullmatch(request["item"])):
        raise ValueError("play requires kind and catalog item name")
    return [MEDIA, action, request["kind"], request["item"]]


def ready():
    result = subprocess.run([HEALTH, "--assert-ready"], capture_output=True,
                            text=True, timeout=5, check=True)
    state = json.loads(result.stdout)
    battery = state["battery"]
    floor = 25 if battery["current_mA_signed"] > 0 else 50
    if (state.get("issues") or battery["capacity_percent"] < floor or
            battery["temperature_mC"] >= 35000 or state["thermal"]["max_mC"] >= 45000):
        raise RuntimeError("power or thermal guard failed")
    return state["boot_id"]


def compact(action, payload):
    if not payload.get("ok"):
        raise RuntimeError(str(payload.get("error", "media command failed"))[:200])
    if action == "catalog":
        return {"ok": True, "sounds": sorted(payload.get("sounds", {})),
                "images": sorted(payload.get("images", {}))}
    if action == "status":
        channels = payload.get("channels", {})
        return {"ok": True, "channels": {kind: {"mode": item.get("mode"),
                       "current": item.get("current"), "queue_count": len(item.get("queue", []))}
                       for kind, item in channels.items()}, "errors": payload.get("errors", [])[:3]}
    channel = payload.get("channel", {})
    return {"ok": True, "channel": {"mode": channel.get("mode"),
                                    "current": channel.get("current"),
                                    "queue_count": len(channel.get("queue", []))}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=ACTIONS)
    action = parser.parse_args(argv).action
    try:
        raw = sys.stdin.read(2049)
        if len(raw) > 2048:
            raise ValueError("request too large")
        command = arguments(action, json.loads(raw or "{}"))
        boot_id = ready() if action == "play" else None
        result = subprocess.run(command, capture_output=True, text=True, timeout=5, check=True)
        output = compact(action, json.loads(result.stdout))
        if boot_id:
            output["boot_id"] = boot_id
        print(json.dumps(output, sort_keys=True, separators=(",", ":")))
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired,
            subprocess.CalledProcessError) as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__,
                          "detail": str(exc)[:160]}, separators=(",", ":")))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
