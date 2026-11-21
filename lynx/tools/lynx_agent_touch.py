#!/usr/bin/env python3
"""Non-consuming touch state for Lynx's local agent (TOUCH_STATUS only).

Reads the runtime's touch queue state over the local NRP socket without
removing any event. It never sends TOUCH_POLL (381), which pops the shared
queue (see lynx/linux-port/docs/LYNX-TOUCH-EVENTS-DESIGN-20261121.md).

Output (one JSON line):
  {"ok":true,"panel_open":true,"finger_down":false,"queued":0,"dropped":0,
   "consumes_events":false}
"""

import json
import re
import socket
import sys

SOCKET = "/run/lynx/noobd.sock"
COMMAND = "CALL TOUCH_STATUS"
REPLY = re.compile(r"NRP/1 7 OK value=(-?\d+)(?: detail=([^\r\n]*))?\Z")
DETAIL = re.compile(r"panel=(\S+) down=([01]) queued=(\d+) dropped=(\d+)\Z")


def nrp(command, path=SOCKET, timeout=2.0):
    """Send one NRP/1 line on the local socket and return the reply line."""
    if command != COMMAND:
        raise ValueError("only TOUCH_STATUS is allowed")
    with socket.socket(socket.AF_UNIX) as conn:
        conn.settimeout(timeout)
        conn.connect(path)
        conn.sendall(("NRP/1 7 " + command + "\n").encode("ascii"))
        with conn.makefile("rb") as stream:
            for _ in range(4):
                data = stream.readline(4097)
                if not data.startswith(b"NRP/1 0 EVENT "):
                    break
    if len(data) > 4096 or not data.endswith(b"\n"):
        raise RuntimeError("incomplete NRP reply")
    return data.decode("ascii").rstrip("\n")


def parse(reply):
    match = REPLY.fullmatch(reply)
    if match is None:
        raise RuntimeError("TOUCH_STATUS call failed")
    detail = DETAIL.fullmatch(match.group(2) or "")
    if detail is None:
        raise RuntimeError("unexpected TOUCH_STATUS detail")
    queued, dropped = int(detail.group(3)), int(detail.group(4))
    if queued > 8:
        raise RuntimeError("queue count exceeds runtime capacity")
    return {"ok": True, "panel_open": match.group(1) == "1",
            "finger_down": detail.group(2) == "1", "queued": queued,
            "dropped": dropped, "consumes_events": False}


def main(argv=None, call=nrp):
    try:
        raw = sys.stdin.read(257)
        if len(raw) > 256 or json.loads(raw or "{}") != {}:
            raise ValueError("no arguments accepted")
        output = parse(call(COMMAND))
        print(json.dumps(output, separators=(",", ":")))
        return 0
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__,
                          "detail": str(exc)[:160]}, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
