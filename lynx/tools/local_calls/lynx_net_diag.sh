#!/bin/sh
# Entity: Lynx. Network diagnostic toolkit wrapper for agent JSON protocol.
exec /usr/bin/python3 -c '
import json, sys, subprocess

payload = json.loads(sys.stdin.read(4096) or "{}")
action = payload.get("action", "lan-sweep")
cmd = ["/usr/local/bin/lynx-net-diag", action]

if action == "port-scan":
    cmd.append(payload.get("target", "192.168.100.1"))
    if "ports" in payload:
        cmd.extend(["--ports", payload["ports"]])
elif action == "traceroute":
    if "target" in payload:
        cmd.append(payload["target"])
elif action == "dns-audit":
    if "domain" in payload:
        cmd.extend(["--domain", payload["domain"]])
elif action == "packet-sample":
    if "count" in payload:
        cmd.extend(["--count", str(payload["count"])])

res = subprocess.run(cmd, capture_output=True, text=True, timeout=18)
print(res.stdout if res.returncode == 0 else json.dumps({"ok": False, "error": res.stderr}))
'
