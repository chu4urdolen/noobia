#!/bin/sh
# Entity: Lynx. Network diagnostic toolkit wrapper for agent JSON protocol.
exec /usr/bin/python3 -c '
import json, sys, subprocess

payload = json.loads(sys.stdin.read(4096) or "{}")
action = payload.get("action", "net-ifaces")
cmd = ["/usr/local/bin/lynx-net-diag"]

if payload.get("fork"):
    cmd.append("--fork")

cmd.append(action)

if action == "port-scan":
    cmd.append(payload.get("target", "192.168.100.106"))
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
elif action == "vuln-check":
    if "target" in payload:
        cmd.append(payload["target"])
elif action == "ssl-audit":
    if "host" in payload:
        cmd.append(payload["host"])
    if "port" in payload:
        cmd.extend(["--port", str(payload["port"])])
elif action == "lan-sweep":
    if "iface" in payload:
        cmd.extend(["--iface", payload["iface"]])
elif action == "wifi-recon":
    if "iface" in payload:
        cmd.extend(["--iface", payload["iface"]])

try:
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=18)
    print(res.stdout if res.returncode == 0 else json.dumps({"ok": False, "error": res.stderr, "sentence": "Diagnostic command encountered an error."}))
except subprocess.TimeoutExpired:
    print(json.dumps({"ok": False, "error": "timeout", "sentence": "Diagnostic scan timed out after 18s."}))
except Exception as e:
    print(json.dumps({"ok": False, "error": str(e), "sentence": f"Error running diagnostic: {e}"}))
'
