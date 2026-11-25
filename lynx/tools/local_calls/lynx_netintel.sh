#!/bin/sh
# Entity: Lynx. Network and radio intelligence (Rose's backlog; Gwyn 2026-11-25).
exec /usr/bin/python3 -c '
import json, subprocess, sys
p = json.loads(sys.stdin.read(4096) or "{}")
action = p.get("action", "stats")
if action not in ("stats", "doctor", "discover", "radios", "ble-scan", "cell"):
    print(json.dumps({"ok": False, "error": "unknown action"})); sys.exit(1)
cmd = ["/usr/bin/python3", "/usr/local/lib/noobia/netintel/lynx_netintel.py", action]
if action == "ble-scan":
    cmd.append(str(max(3, min(15, float(p.get("seconds", 8))))))
try:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=28)
    print(r.stdout.strip() or json.dumps({"ok": False, "error": r.stderr.strip()[-300:]}))
except subprocess.TimeoutExpired:
    print(json.dumps({"ok": False, "error": "timeout after 28 s"}))
'
