#!/usr/bin/env python3
"""Talk to LAFVIN's SpiderBot HTTP API over its local Wi-Fi access point."""

import argparse
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request


def request(host: str, path: str, payload: dict | None, timeout: float) -> dict:
    url = f"http://{host}{path}"
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {} if data is None else {"Content-Type": "application/json"}
    method = "GET" if data is None else "POST"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise ValueError(f"HTTP {error.code}: {body}") from error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="192.168.4.1")
    parser.add_argument("--timeout", type=float, default=5)
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("info", help="list firmware details and available actions")
    commands.add_parser("state", help="read current and requested action")
    commands.add_parser("servos", help="read eight last-commanded servo angles (not feedback)")
    commands.add_parser("distance", help="read the ultrasonic sensor in millimetres")
    calibration = commands.add_parser("calibration", help="read or change saved servo offsets")
    calibration_changes = calibration.add_subparsers(dest="calibration_command")
    for change in ("set", "add"):
        calibration_change = calibration_changes.add_parser(
            change, help="set an absolute offset" if change == "set" else "add a relative offset")
        calibration_change.add_argument("servo", type=int, help="zero-based servo ID, 0 through 7")
        calibration_change.add_argument("degrees", type=int, help="signed degrees")
    action = commands.add_parser("action", help="run one named factory action")
    action.add_argument("name")
    servo = commands.add_parser("servo", help="set one servo to an absolute angle")
    servo.add_argument("number", type=int, help="Lolth servo number, 1 through 8")
    servo.add_argument("angle", type=int, help="absolute electrical angle, 1 through 180")
    for direction in ("up", "down"):
        step = commands.add_parser(direction, help=f"move one servo's electrical angle {direction}")
        step.add_argument("number", type=int, help="Lolth servo number, 1 through 8")
        step.add_argument("degrees", type=int, help="step size, 1 through 20")
    program = commands.add_parser("program", help="preview or run a saved servo pose")
    program.add_argument("file", type=Path)
    program.add_argument("--servo", type=int, help="apply only this one servo")
    program.add_argument("--all", action="store_true", help="apply every servo in the pose")
    program.add_argument("--execute", action="store_true", help="send physical motion commands")
    stop = commands.add_parser("stop", help="request an action stop and target pose")
    stop.add_argument("mode", choices=("standby", "center", "zero"), default="standby", nargs="?")
    args = parser.parse_args()

    if args.command in (None, "info"):
        path, payload = "/api/v1/info", None
    elif args.command == "state":
        path, payload = "/api/v1/state", None
    elif args.command == "servos":
        path, payload = "/api/v1/servos", None
    elif args.command == "distance":
        path, payload = "/api/v1/distance", None
    elif args.command == "calibration":
        if args.calibration_command is not None:
            if not 0 <= args.servo <= 7:
                parser.error("calibration servo ID must be 0..7")
            try:
                before = request(args.host, "/api/v1/calibration", None, args.timeout)
                if before.get("ok") is not True:
                    raise ValueError(f"calibration read failed: {before}")
                offsets = before["data"]["offsets"]
                if len(offsets) != 8 or any(type(value) is not int for value in offsets):
                    raise ValueError("invalid calibration offsets from Lolth")
                old = offsets[args.servo]
                new = args.degrees if args.calibration_command == "set" else old + args.degrees
                if not -124 <= new <= 124:
                    parser.error(f"resulting offset {new} is outside firmware range -124..124")
                offsets[args.servo] = new
                if new != old:
                    saved = request(args.host, "/api/v1/calibration", {"offsets": offsets}, args.timeout)
                    if saved.get("ok") is not True:
                        raise ValueError(f"calibration write failed: {saved}")
                checked = request(args.host, "/api/v1/calibration", None, args.timeout)
                if checked.get("ok") is not True or checked["data"]["offsets"] != offsets:
                    raise ValueError(f"calibration readback differs: {checked}")
                print(json.dumps({"servo": args.servo, "before": old, "after": new,
                                  "offsets": offsets, "verified": True}, indent=2))
                return 0
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
                print(f"lafvinctl: {error}", file=sys.stderr)
                return 1
        path, payload = "/api/v1/calibration", None
    elif args.command == "action":
        path, payload = "/api/v1/action", {"action": args.name}
    elif args.command == "servo":
        if not 1 <= args.number <= 8 or not 1 <= args.angle <= 180:
            parser.error("servo number must be 1..8 and angle must be 1..180")
        path, payload = "/api/v1/servo", {"servo": args.number - 1, "value": args.angle}
    elif args.command in ("up", "down"):
        if not 1 <= args.number <= 8 or not 1 <= args.degrees <= 20:
            parser.error("servo number must be 1..8 and step must be 1..20 degrees")
        delta = args.degrees if args.command == "up" else -args.degrees
        path, payload = "/api/v1/servo/step", {"servo": args.number - 1, "delta": delta}
    elif args.command == "program":
        try:
            program_data = json.loads(args.file.read_text(encoding="utf-8"))
            targets = program_data["targets"]
            selected = [(int(number), int(angle)) for number, angle in targets.items()]
        except (OSError, ValueError, KeyError, AttributeError, TypeError) as error:
            parser.error(f"invalid program: {error}")
        if len(selected) != len(targets) or len({number for number, _ in selected}) != len(selected):
            parser.error("program has duplicate servo numbers")
        if any(not 1 <= number <= 8 or not 1 <= angle <= 180 for number, angle in selected):
            parser.error("program servo numbers must be 1..8 and angles 1..180")
        if args.servo is not None:
            selected = [(number, angle) for number, angle in selected if number == args.servo]
            if not selected:
                parser.error("selected servo is not in the program")
        elif args.execute and not args.all:
            parser.error("physical execution requires --servo NUMBER or --all")
        selected.sort()
        if not args.execute:
            print(json.dumps({"name": program_data.get("name", args.file.stem),
                              "would_send": selected, "executed": False}, indent=2))
            return 0
        try:
            for number, angle in selected:
                result = request(args.host, "/api/v1/servo",
                                 {"servo": number - 1, "value": angle}, args.timeout)
                print(json.dumps(result, ensure_ascii=False))
                if result.get("ok") is not True:
                    return 1
            return 0
        except (OSError, ValueError, json.JSONDecodeError) as error:
            print(f"lafvinctl: {error}", file=sys.stderr)
            return 1
    else:
        path, payload = "/api/v1/stop", {"mode": args.mode}

    try:
        result = request(args.host, path, payload, args.timeout)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") is True else 1
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"lafvinctl: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
