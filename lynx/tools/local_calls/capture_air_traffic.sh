#!/bin/sh
exec /usr/bin/python3 -c '
import json, sys, subprocess

payload = json.loads(sys.stdin.read(4096) or "{}")
cmd = ["/usr/local/bin/lynx-capture-air-traffic"]

if payload.get("fork"):
    cmd.append("--fork")
if "seconds" in payload:
    cmd.extend(["--seconds", str(payload["seconds"])])
if "interface" in payload:
    cmd.extend(["--interface", str(payload["interface"])])

try:
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=65)
    print(res.stdout if res.returncode == 0 else json.dumps({"ok": False, "error": res.stderr, "sentence": "Air capture encountered an error."}))
except subprocess.TimeoutExpired:
    print(json.dumps({"ok": False, "error": "timeout", "sentence": "Air traffic capture timed out."}))
except Exception as e:
    print(json.dumps({"ok": False, "error": str(e), "sentence": f"Error running air capture: {e}"}))
'
