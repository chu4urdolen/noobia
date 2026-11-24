#!/bin/sh
# Entity: Lynx. Cellular & 5G diagnostic toolkit wrapper for agent JSON protocol.
exec /usr/bin/python3 -c '
import json, sys, subprocess

payload = json.loads(sys.stdin.read(4096) or "{}")
action = payload.get("action", "sim-check")
cmd = ["/usr/local/bin/lynx-cellular-diag"]

if payload.get("fork"):
    cmd.append("--fork")

cmd.append(action)

try:
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    print(res.stdout if res.returncode == 0 else json.dumps({"ok": False, "error": res.stderr, "sentence": "Cellular diagnostic encountered an error."}))
except subprocess.TimeoutExpired:
    print(json.dumps({"ok": False, "error": "timeout", "sentence": "Cellular diagnostic timed out."}))
except Exception as e:
    print(json.dumps({"ok": False, "error": str(e), "sentence": f"Error running cellular diagnostic: {e}"}))
'
