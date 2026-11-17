#!/usr/bin/env python3
"""Nexus Network Defense Audit & Noobia Wi-Fi Stability Watchdog.

Co-developed by Dushich and Banshee on Nexus.
Audits kernel sysctl hardening, UFW firewall rules, Fail2ban intrusion
prevention, SSH hardening, and Noobia Wi-Fi (`wlx40a5ef5f66f1` /
`192.168.100.106`) stability, with optional `--heal-wifi` auto-recovery so
all Noobs on `192.168.100.0/24` maintain a rock-solid connection to Nexus.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time


NOOBIA_IFACE = "wlx40a5ef5f66f1"
NOOBIA_PROFILE = "Noobia MT7612U"
NOOBIA_STATIC_IP = "192.168.100.106"
NOOBIA_GATEWAY = "192.168.100.1"
TRUSTED_SUBNETS = ("192.168.100.0/24", "192.168.4.0/24")

REQUIRED_SYSCTLS = {
    "net.ipv4.tcp_syncookies": "1",
    "net.ipv4.conf.all.rp_filter": "1",
    "net.ipv4.conf.all.accept_redirects": "0",
    "net.ipv4.conf.all.send_redirects": "0",
    "net.ipv4.conf.all.accept_source_route": "0",
    "net.ipv4.icmp_echo_ignore_broadcasts": "1",
    "net.ipv4.tcp_rfc1337": "1",
    "net.ipv6.conf.all.accept_redirects": "0",
    "net.ipv6.conf.all.accept_source_route": "0",
}


def _run(cmd: list[str], timeout: int = 8) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PATH"] = "/usr/sbin:/sbin:/usr/bin:/bin:" + env.get("PATH", "")
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return subprocess.CompletedProcess(cmd, 1, "", str(exc))


def read_live_sysctls(keys: list[str] | tuple[str, ...] = tuple(REQUIRED_SYSCTLS)) -> dict[str, str]:
    values: dict[str, str] = {}
    for key in keys:
        proc_path = Path("/proc/sys") / key.replace(".", "/")
        try:
            values[key] = proc_path.read_text(encoding="ascii").strip()
        except OSError:
            pass
    return values


def parse_sysctl_hardening(sysctl_map: dict[str, str]) -> dict:
    checks: dict[str, bool] = {}
    missing: list[str] = []
    for key, expected in REQUIRED_SYSCTLS.items():
        actual = sysctl_map.get(key)
        if actual == expected:
            checks[key] = True
        else:
            checks[key] = False
            missing.append(key)
    return {
        "ok": len(missing) == 0,
        "checks": checks,
        "missing_or_weak": missing,
    }


def evaluate_ufw_status(ufw_text: str) -> dict:
    status_ok = "Status: active" in ufw_text
    default_incoming_ok = "deny (incoming)" in ufw_text
    subnet_ok = {subnet: (subnet in ufw_text) for subnet in TRUSTED_SUBNETS}
    ssh_limit_ok = "22/tcp" in ufw_text and "LIMIT IN" in ufw_text
    ok = status_ok and default_incoming_ok and all(subnet_ok.values()) and ssh_limit_ok
    return {
        "ok": ok,
        "status_ok": status_ok,
        "default_incoming_ok": default_incoming_ok,
        "subnet_ok": subnet_ok,
        "ssh_limit_ok": ssh_limit_ok,
    }


def evaluate_noobia_wifi(nmcli_dev_text: str, ip_addr_text: str, powersave_text: str) -> dict:
    dev_connected = (
        NOOBIA_IFACE in nmcli_dev_text
        and NOOBIA_PROFILE in nmcli_dev_text
        and "connected" in nmcli_dev_text
    )
    ip_ok = NOOBIA_STATIC_IP in ip_addr_text
    powersave_ok = "power save: off" in powersave_text.lower()
    ok = dev_connected and ip_ok and powersave_ok
    return {
        "ok": ok,
        "dev_connected": dev_connected,
        "ip_ok": ip_ok,
        "powersave_ok": powersave_ok,
    }


def evaluate_fail2ban(service_active: str, jail_text: str) -> dict:
    active_ok = service_active.strip() == "active"
    sshd_jail_ok = "Status for the jail: sshd" in jail_text
    return {
        "ok": active_ok and sshd_jail_ok,
        "service_active": active_ok,
        "sshd_jail_ok": sshd_jail_ok,
    }

# ---------------------------------------------------------------------------
# Listener exposure verification
# ---------------------------------------------------------------------------
def evaluate_listeners(ss_text: str) -> dict:
    """Evaluate socket listener exposure.

    Parameters
    ----------
    ss_text:
        Raw output from ``ss -tln``.

    Returns
    -------
    dict
        Mapping of ``ok`` and the individual checks:
        ``ssh_listening`` – ``:22`` present.
        ``inference_proxy_lan_ok`` – ``192.168.100.106:8080`` present **and**
        ``0.0.0.0:8080`` absent.
        ``ollama_localhost_only`` – ``127.0.0.1:11434`` present **and**
        ``0.0.0.0:11434`` absent.
    """
    ssh_listening = ":22" in ss_text
    inference_proxy_lan_ok = (
        "192.168.100.106:8080" in ss_text and "0.0.0.0:8080" not in ss_text
    )
    ollama_localhost_only = (
        "127.0.0.1:11434" in ss_text and "0.0.0.0:11434" not in ss_text
    )
    ok = ssh_listening and inference_proxy_lan_ok and ollama_localhost_only
    return {
        "ok": ok,
        "ssh_listening": ssh_listening,
        "inference_proxy_lan_ok": inference_proxy_lan_ok,
        "ollama_localhost_only": ollama_localhost_only,
    }


def check_once(heal_wifi: bool = False) -> dict:
    sysctl_res = parse_sysctl_hardening(read_live_sysctls())

    ufw_out = _run(["sudo", "-n", "/usr/sbin/ufw", "status", "verbose"])
    ufw_res = evaluate_ufw_status(ufw_out.stdout)

    f2b_active = _run(["systemctl", "is-active", "fail2ban"]).stdout
    f2b_jail = _run(["sudo", "-n", "/usr/bin/fail2ban-client", "status", "sshd"]).stdout
    f2b_res = evaluate_fail2ban(f2b_active, f2b_jail)

    nmcli_out = _run(["nmcli", "-t", "-f", "DEVICE,STATE,CONNECTION", "device", "status"])
    ip_out = _run(["ip", "-4", "-br", "addr", "show", NOOBIA_IFACE])
    iw_out = _run(["/usr/sbin/iw", "dev", NOOBIA_IFACE, "get", "power_save"])
    wifi_res = evaluate_noobia_wifi(nmcli_out.stdout, ip_out.stdout, iw_out.stdout)

    healed = False
    if heal_wifi and not wifi_res["ok"]:
        if not wifi_res["dev_connected"] or not wifi_res["ip_ok"]:
            _run(
                [
                    "sudo",
                    "-n",
                    "nmcli",
                    "--wait",
                    "10",
                    "connection",
                    "up",
                    NOOBIA_PROFILE,
                    "ifname",
                    NOOBIA_IFACE,
                ],
                timeout=14,
            )
            healed = True
        if not wifi_res["powersave_ok"] or healed:
            _run(["sudo", "-n", "/usr/sbin/iw", "dev", NOOBIA_IFACE, "set", "power_save", "off"])
            healed = True
        nmcli_out = _run(["nmcli", "-t", "-f", "DEVICE,STATE,CONNECTION", "device", "status"])
        ip_out = _run(["ip", "-4", "-br", "addr", "show", NOOBIA_IFACE])
        iw_out = _run(["/usr/sbin/iw", "dev", NOOBIA_IFACE, "get", "power_save"])
        wifi_res = evaluate_noobia_wifi(nmcli_out.stdout, ip_out.stdout, iw_out.stdout)

    ping_out = _run(["ping", "-c", "1", "-W", "2", "-I", NOOBIA_IFACE, NOOBIA_GATEWAY])
    ping_ok = ping_out.returncode == 0

    # Listener exposure check
    ss_out = _run(["ss", "-tln"])
    listeners_res = evaluate_listeners(ss_out.stdout)

    healthy = (
        sysctl_res["ok"]
        and ufw_res["ok"]
        and f2b_res["ok"]
        and wifi_res["ok"]
        and ping_ok
        and listeners_res["ok"]
    )
    return {
        "healthy": healthy,
        "sysctl": sysctl_res,
        "ufw": ufw_res,
        "fail2ban": f2b_res,
        "wifi": wifi_res,
        "gateway_ping_ok": ping_ok,
        "listeners": listeners_res,
        "healed": healed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print JSON status report")
    parser.add_argument("--once", action="store_true", help="Run one check and exit")
    parser.add_argument("--watch", action="store_true", help="Run periodic monitoring")
    parser.add_argument("--interval", type=int, default=15, help="Watch interval in seconds")
    parser.add_argument("--heal-wifi", action="store_true", help="Auto-heal Noobia Wi-Fi if degraded")
    args = parser.parse_args()

    while True:
        res = check_once(heal_wifi=args.heal_wifi)
        if args.json:
            print(json.dumps(res, indent=2), flush=True)
        else:
            print(
                f"[nexus-net-guard] healthy={res['healthy']} "
                f"sysctl={res['sysctl']['ok']} ufw={res['ufw']['ok']} "
                f"fail2ban={res['fail2ban']['ok']} wifi={res['wifi']['ok']} "
                f"gateway_ping={res['gateway_ping_ok']} healed={res['healed']}",
                flush=True,
            )
        if args.once or not args.watch:
            return 0 if res["healthy"] else 1
        time.sleep(max(3, args.interval))


if __name__ == "__main__":
    sys.exit(main())
