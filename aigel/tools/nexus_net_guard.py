#!/usr/bin/env python3
"""Nexus Network Defense Audit & Noobia Wi-Fi Stability Watchdog.

Co-developed by Dushich and Banshee on Nexus.
Audits kernel sysctl hardening, UFW firewall rules, Fail2ban intrusion
prevention, SSH hardening, Noobia Wi-Fi (`wlx40a5ef5f66f1` /
`192.168.100.106`) stability, socket listener exposure, Wi-Fi link signal
quality (RSSI), ARP neighbor integrity (spoofing detection), and defense
config file integrity, with optional `--heal-wifi` auto-recovery so all
Noobs on `192.168.100.0/24` maintain a rock-solid connection to Nexus.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
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
        ``ssh_listening`` -- ``:22`` present.
        ``inference_proxy_lan_ok`` -- ``192.168.100.106:8080`` present **and**
        ``0.0.0.0:8080`` absent.
        ``ollama_localhost_only`` -- ``127.0.0.1:11434`` present **and**
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


# ---------------------------------------------------------------------------
# Wi-Fi link signal quality (RSSI)
# ---------------------------------------------------------------------------
_WIFI_SIGNAL_RE = re.compile(r"signal:\s*(-?\d+)\s*dBm", re.IGNORECASE)


def evaluate_wifi_signal(iw_link_text: str) -> dict:
    """Evaluate the quality of the Noobia Wi-Fi link from `iw dev ... link`.

    Parameters
    ----------
    iw_link_text:
        Raw output from ``iw dev wlx40a5ef5f66f1 link``.

    Returns
    -------
    dict
        ``ok`` -- True when the radio is connected with a strong signal
        (``rssi_dbm >= -75``) or connected with no signal line to parse.
        ``rssi_dbm`` -- parsed integer RSSI in dBm, or ``None``.
        ``strong_signal`` -- True when RSSI is at least -75 dBm (or no
        signal line is present while connected).
    """
    if "Not connected" in iw_link_text:
        return {"ok": False, "rssi_dbm": None, "strong_signal": False}
    match = _WIFI_SIGNAL_RE.search(iw_link_text)
    if match:
        rssi_dbm = int(match.group(1))
        strong_signal = rssi_dbm >= -75
        return {"ok": strong_signal, "rssi_dbm": rssi_dbm, "strong_signal": strong_signal}
    # Connected (not "Not connected") but no parsable signal line: assume
    # the link is fine rather than failing on an unusual formatter.
    return {"ok": True, "rssi_dbm": None, "strong_signal": True}


# ---------------------------------------------------------------------------
# ARP neighbor integrity (spoofing detection)
# ---------------------------------------------------------------------------
_ARP_NEIGH_RE = re.compile(r"^(\d{1,3}(?:\.\d{1,3}){3})\s+lladdr\s+([0-9a-fA-F:]{17})")


def evaluate_arp_neighbors(ip_neigh_text: str) -> dict:
    """Evaluate `ip -4 neigh show dev <iface>` output for spoofing signs.

    Parameters
    ----------
    ip_neigh_text:
        Raw output from ``ip -4 neigh show dev wlx40a5ef5f66f1``.
        Lines look like ``192.168.100.1 lladdr 48:ad:08:d8:1f:6c REACHABLE``.

    Returns
    -------
    dict
        ``ok`` -- gateway present **and** no MAC claimed by more than one IP.
        ``gateway_present`` -- the Noobia gateway 192.168.100.1 is resolvable.
        ``neighbor_count`` -- number of resolved (lladdr) neighbor entries.
        ``duplicate_macs`` -- sorted list of MACs bound to more than one IP.
    """
    ip_to_mac: dict[str, str] = {}
    mac_to_ips: dict[str, list[str]] = {}
    for line in ip_neigh_text.splitlines():
        if "lladdr" not in line:
            continue
        match = _ARP_NEIGH_RE.match(line.strip())
        if not match:
            continue
        ip_addr, mac = match.group(1), match.group(2).lower()
        ip_to_mac[ip_addr] = mac
        mac_to_ips.setdefault(mac, []).append(ip_addr)

    duplicate_macs = sorted(mac for mac, ips in mac_to_ips.items() if len(ips) > 1)
    gateway_present = NOOBIA_GATEWAY in ip_to_mac
    return {
        "ok": gateway_present and len(duplicate_macs) == 0,
        "gateway_present": gateway_present,
        "neighbor_count": len(ip_to_mac),
        "duplicate_macs": duplicate_macs,
    }


# ---------------------------------------------------------------------------
# Defense config integrity (SHA-256)
# ---------------------------------------------------------------------------
DEFAULT_DEFENSE_CONFIGS = (
    "/etc/NetworkManager/conf.d/90-noobia-wifi-powersave-off.conf",
    "/etc/fail2ban/jail.d/90-nexus-defense.local",
    "/etc/ssh/sshd_config.d/90-nexus-hardening.conf",
    "/etc/sysctl.d/90-nexus-network-security.conf",
)


def evaluate_config_integrity(
    paths: list[str] | tuple[str, ...] = DEFAULT_DEFENSE_CONFIGS,
) -> dict:
    """Verify the defense hardening config files exist, are non-empty, and
    record their SHA-256 digests.

    Parameters
    ----------
    paths:
        Config files to check (defaults to ``DEFAULT_DEFENSE_CONFIGS``).

    Returns
    -------
    dict
        ``ok`` -- every path exists with size > 0.
        ``missing`` -- paths that are absent or empty (in input order).
        ``sha256`` -- mapping of path -> hex digest (``None`` when missing).
    """
    missing: list[str] = []
    digests: dict[str, str | None] = {}
    for path in paths:
        try:
            file_path = Path(path)
            if not file_path.is_file() or file_path.stat().st_size == 0:
                missing.append(path)
                digests[path] = None
                continue
            hasher = hashlib.sha256()
            with file_path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(65536), b""):
                    hasher.update(chunk)
            digests[path] = hasher.hexdigest()
        except OSError:
            missing.append(path)
            digests[path] = None
    return {
        "ok": len(missing) == 0,
        "missing": missing,
        "sha256": digests,
    }


def derive_verdict(healthy: bool, healed: bool, sections: dict, ping_ok: bool) -> tuple[str, list[str]]:
    """Summarize a ``check_once`` report into one verdict with short reasons.

    ``ok``   — every check passes.
    ``warn`` — everything passes now, but Wi-Fi was degraded and auto-healed
               during the check.
    ``fail`` — any check (including the gateway ping) is not passing.
    """
    reasons: list[str] = []
    for name, res in sections.items():
        if isinstance(res, dict) and res.get("ok") is False:
            text = f"{name} failed"
            missing = res.get("missing")
            if isinstance(missing, list) and missing:
                text += ": " + ", ".join(str(item) for item in missing[:4])
            reasons.append(text)
    if not ping_ok:
        reasons.append("gateway ping failed")
    if not reasons:
        if healed:
            return "warn", ["wifi was degraded and was auto-healed during this check"]
        return "ok", []
    return "fail", reasons


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

    # Wi-Fi link signal quality (RSSI telemetry)
    iw_link_out = _run(["/usr/sbin/iw", "dev", NOOBIA_IFACE, "link"])
    wifi_signal_res = evaluate_wifi_signal(iw_link_out.stdout)

    # ARP neighbor integrity (spoofing detection)
    neigh_out = _run(["ip", "-4", "neigh", "show", "dev", NOOBIA_IFACE])
    arp_res = evaluate_arp_neighbors(neigh_out.stdout)

    # Defense config integrity (SHA-256 guard)
    config_res = evaluate_config_integrity()

    healthy = (
        sysctl_res["ok"]
        and ufw_res["ok"]
        and f2b_res["ok"]
        and wifi_res["ok"]
        and ping_ok
        and listeners_res["ok"]
        and wifi_signal_res["ok"]
        and arp_res["ok"]
        and config_res["ok"]
    )
    sections = {
        "sysctl": sysctl_res,
        "ufw": ufw_res,
        "fail2ban": f2b_res,
        "wifi": wifi_res,
        "listeners": listeners_res,
        "wifi_signal": wifi_signal_res,
        "arp_neighbors": arp_res,
        "config_integrity": config_res,
    }
    verdict, reasons = derive_verdict(healthy, healed, sections, ping_ok)
    return {
        "healthy": healthy,
        "verdict": verdict,
        "reasons": reasons,
        "sysctl": sysctl_res,
        "ufw": ufw_res,
        "fail2ban": f2b_res,
        "wifi": wifi_res,
        "gateway_ping_ok": ping_ok,
        "listeners": listeners_res,
        "wifi_signal": wifi_signal_res,
        "arp_neighbors": arp_res,
        "config_integrity": config_res,
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
                f"[nexus-net-guard] verdict={res['verdict']} healthy={res['healthy']} "
                f"sysctl={res['sysctl']['ok']} ufw={res['ufw']['ok']} "
                f"fail2ban={res['fail2ban']['ok']} wifi={res['wifi']['ok']} "
                f"gateway_ping={res['gateway_ping_ok']} listeners={res['listeners']['ok']} "
                f"wifi_signal={res['wifi_signal']['ok']} "
                f"arp={res['arp_neighbors']['ok']} "
                f"config={res['config_integrity']['ok']} healed={res['healed']}"
                + (f" reasons={'; '.join(res['reasons'])}" if res["reasons"] else ""),
                flush=True,
            )
        if args.once or not args.watch:
            return 0 if res["healthy"] else 1
        time.sleep(max(3, args.interval))


if __name__ == "__main__":
    sys.exit(main())
