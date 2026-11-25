#!/usr/bin/env python3
"""lynx-tool-policy: who and what Lynx's network tools may touch (LNX-25).

Rose's backlog, rule 7 "Security testing requires authorized targets" and rule
10 "Security observations must be traceable" (Gwyn, 2026-11-25).

Every network tool asks `authorize(action, target)` before acting:

* **Probing actions** (port-scan, vuln-check) only against authorized targets:
  Lynx herself and the Noobia LAN (192.168.100.0/24 by default).
* **Path checks** (traceroute, dns-audit, ssl-audit) may also reach public
  addresses: they are ordinary connectivity checks, not attacks. Private
  networks outside Noobia stay refused.
* **Passive local views** (net-ifaces, lan-sweep, wifi-recon) need no target.
* **packet-sample** (tcpdump) captures other people's traffic too, so it is
  OFF until a person sets "allow_packet_capture": true (Principle 8).
* Anything unknown is refused. If the policy cannot be read, probing and
  capture are refused (fail closed); passive views still work.

Every decision, allowed or refused, is appended to the audit log
(/var/log/lynx-tool-policy.jsonl): time, tool, action, target, resolved
address, decision, reason. Never the tool's output.

Policy file (optional): /etc/lynx/tool-policy.json, e.g.
    {"authorized_networks": ["192.168.100.0/24"], "allow_packet_capture": false}

CLI (for people and tests):
    lynx-tool-policy check ACTION [TARGET]     -> JSON decision, exit 0 allowed / 3 refused
"""
from __future__ import annotations

import ipaddress
import json
import os
from pathlib import Path
import socket
import sys
import time

POLICY_FILE = Path(os.environ.get("LYNX_TOOL_POLICY", "/etc/lynx/tool-policy.json"))
AUDIT_LOG = Path(os.environ.get("LYNX_TOOL_POLICY_LOG", "/var/log/lynx-tool-policy.jsonl"))
DEFAULTS = {
    "authorized_networks": ["192.168.100.0/24"],
    "self_addresses": ["127.0.0.0/8", "::1/128", "192.168.100.107/32"],
    "allow_packet_capture": False,
}
# Passive views of her own state, plus link-local discovery that by its nature never
# leaves the LAN (mDNS/SSDP multicast, a bounded Bluetooth scan) - Gwyn 2026-11-25.
PASSIVE = {"net-ifaces", "lan-sweep", "wifi-recon", "traffic-stats", "radios", "cell-status",
           "net-doctor", "service-discovery", "ble-scan"}
PROBING = {"port-scan", "vuln-check", "noob-discovery"}
PATH_CHECKS = {"traceroute", "dns-audit", "ssl-audit"}
CAPTURE = {"packet-sample"}


def load_policy(path: Path = POLICY_FILE) -> tuple[dict, str | None]:
    """(policy, error). A missing file means the defaults; a broken file is an error."""
    policy = dict(DEFAULTS)
    if not path.exists():
        return policy, None
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict):
            raise ValueError("policy must be a JSON object")
        for key in ("authorized_networks", "self_addresses"):
            if key in data:
                [ipaddress.ip_network(n, strict=False) for n in data[key]]
                policy[key] = list(data[key])
        if "allow_packet_capture" in data:
            policy["allow_packet_capture"] = data["allow_packet_capture"] is True
        return policy, None
    except (OSError, ValueError, TypeError) as exc:
        return policy, f"policy file unreadable: {type(exc).__name__}: {str(exc)[:80]}"


def resolve(target: str, resolver=socket.getaddrinfo) -> list[ipaddress._BaseAddress]:
    """All addresses a target name stands for (a name could hide an outside host)."""
    try:
        return [ipaddress.ip_address(target)]
    except ValueError:
        pass
    infos = resolver(target, None)
    return sorted({ipaddress.ip_address(i[4][0].split("%")[0]) for i in infos}, key=str)


def _inside(addrs, networks) -> bool:
    nets = [ipaddress.ip_network(n, strict=False) for n in networks]
    return bool(addrs) and all(any(a in n for n in nets) for a in addrs)


def decide(action: str, target: str | None, policy: dict, policy_error: str | None = None,
           resolver=socket.getaddrinfo) -> tuple[bool, str, list[str]]:
    """(allowed, reason, resolved addresses)."""
    if action in PASSIVE:
        return True, "passive local view", []
    if policy_error:
        return False, f"refused: {policy_error} (fail closed)", []
    if action in CAPTURE:
        if policy.get("allow_packet_capture") is True:
            return True, "packet capture allowed by policy", []
        return False, ("refused: packet capture records other people's traffic; "
                       "a person must set allow_packet_capture in /etc/lynx/tool-policy.json"), []
    if action not in PROBING | PATH_CHECKS:
        return False, f"refused: unknown action {action!r}", []
    if not target:
        return False, "refused: this action needs a target", []
    try:
        addrs = resolve(target, resolver)
    except OSError as exc:
        return False, f"refused: cannot resolve {target!r} ({type(exc).__name__})", []
    shown = [str(a) for a in addrs]
    mine = policy["authorized_networks"] + policy["self_addresses"]
    if _inside(addrs, mine):
        return True, "authorized target (Lynx or the Noobia LAN)", shown
    if action in PROBING:
        return False, (f"refused: {action} only against authorized targets "
                       f"({', '.join(policy['authorized_networks'])} and Lynx herself); "
                       f"{target} is not one (Rose's rule 7)"), shown
    if all(a.is_global for a in addrs):
        return True, "path check to a public address", shown
    return False, f"refused: {target} is a private network outside Noobia", shown


def audit_log(record: dict, path: Path = AUDIT_LOG) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(fd, "a") as fh:
            fh.write(json.dumps(record, separators=(",", ":")) + "\n")
    except OSError:
        pass   # the decision stands even if the log cannot be written


def authorize(tool: str, action: str, target: str | None = None, *, policy_path: Path = POLICY_FILE,
              log_path: Path = AUDIT_LOG, resolver=socket.getaddrinfo) -> tuple[bool, str]:
    """The one call tools make. Logs every decision (rule 10)."""
    policy, error = load_policy(policy_path)
    ok, reason, addrs = decide(action, target, policy, error, resolver)
    audit_log({"t": round(time.time(), 3), "tool": tool, "action": action, "target": target,
               "addresses": addrs, "allowed": ok, "reason": reason, "pid": os.getpid(),
               "ppid": os.getppid()}, log_path)
    return ok, reason


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) < 2 or argv[0] != "check":
        print(json.dumps({"ok": False, "error": "usage: lynx-tool-policy check ACTION [TARGET]"}))
        return 2
    ok, reason = authorize("cli", argv[1], argv[2] if len(argv) > 2 else None)
    print(json.dumps({"allowed": ok, "action": argv[1], "target": argv[2] if len(argv) > 2 else None,
                      "reason": reason}))
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(main())
