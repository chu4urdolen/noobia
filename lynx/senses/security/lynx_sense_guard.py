#!/usr/bin/env python3
"""S11 guard sense for Lynx: resources, configuration, endpoints, probing.

Rose's backlog (Gwyn, 2026-11-25, picked up from Banshee):

- LNX-103 ``resource.exhaustion`` / ``resource.recovered``: memory, RAM disks
  and disks, file handles, processes, load, TCP orphans.
- LNX-71  ``config.changed``: system configuration files added, removed or
  modified (content hash), or a secret's mode/owner changed (secrets are never
  hashed or read, only stat()ed).
- LNX-101 ``endpoint.untrusted``: an established connection to one of Lynx's
  own listening ports from an address that is not on her trusted list.
- LNX-60  ``probe.detected``: service fingerprinting - many connections that
  end before authentication, or a burst of TCP resets / UDP "no port" replies
  (the kernel answering probes of closed ports).

Read-only: /proc, statvfs, file hashes, the dropbear logs Banshee's S10
already reads. Rose's rule 8: observations, not proof of an attack. Rule 9: no
reaction against anyone, she only perceives. Rule 10: every event also goes to
the incident journal (/var/log/lynx/security.jsonl).
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from lynx_sense_kit import Event, band, run_sense  # noqa: E402
from lynx_senses_lib import finish  # noqa: E402

PROC = Path(os.environ.get("LYNX_GUARD_PROC", "/proc"))
ROOT = Path(os.environ.get("LYNX_GUARD_ROOT", "/"))
TRUSTED_FILE = Path("/etc/lynx/trusted-endpoints.json")
TRUSTED_DEFAULT = ["192.168.100.106", "127.0.0.0/8", "::1"]   # Nexus and herself
DROPBEAR_LOGS = ["/run/lynx/alpine-dropbear-2222.log", "/run/lynx/dropbear.log"]

# -- LNX-103: where she can run out, and when it counts -----------------------
# (name, alarm at or above, clear at or below), percentages unless stated.
LIMITS = {
    "memory": (90.0, 80.0),        # % of RAM in use (100 - MemAvailable)
    "file_handles": (80.0, 70.0),  # % of fs.file-max
    "processes": (80.0, 70.0),     # % of kernel.threads-max
    "load": (3.0, 2.0),            # 1-minute load per CPU
    "tcp_orphans": (200, 50),      # orphaned TCP sockets (count)
}
DISK_LIMIT = (90.0, 85.0)          # % used, per mount
MOUNTS = ["/", "/run", "/tmp", "/var/log", "/var/lib"]

# -- LNX-71: what counts as configuration --------------------------------------
CONFIG_GLOBS = [
    "etc/passwd", "etc/group", "etc/hosts", "etc/hostname", "etc/resolv.conf",
    "etc/inittab", "etc/profile", "etc/profile.d/*", "etc/sudoers", "etc/sudoers.d/*",
    "etc/doas.conf", "etc/apk/world", "etc/apk/repositories", "etc/init.d/*",
    "etc/conf.d/*", "etc/runlevels/*/*", "etc/local.d/*", "etc/crontabs/*",
    "etc/sysctl.conf", "etc/sysctl.d/*", "etc/modprobe.d/*", "etc/modules",
    "etc/network/*", "etc/nftables.conf", "etc/nftables.d/*", "etc/iptables/*",
    "etc/dropbear/*", "etc/ssh/*", "etc/lynx/*", "etc/noobia/*", "root/.ssh/*",
]
SECRET_RE = re.compile(r"(\.key|\.secret|_key|wpa_supplicant\.conf|shadow|"
                       r"authorized_keys|host_key[^/]*)$")
MAX_FILES = 600
MAX_HASH_BYTES = 1_000_000
CONFIG_SHOW = 3          # name at most this many paths in one line

# -- LNX-60 ---------------------------------------------------------------------
PROBE_BEFORE_AUTH = 8    # pre-auth exits from one address in one sample
PROBE_RESETS = 100       # TCP OutRsts + UDP NoPorts growth in one sample
SAMPLE_GAP_MAX_S = 300   # a longer gap (asleep, restarted) is not a burst


# == observe ====================================================================

def meminfo(proc: Path) -> dict:
    out = {}
    for line in (proc / "meminfo").read_text().splitlines():
        k, _, v = line.partition(":")
        if v.split():
            out[k] = int(v.split()[0])
    return out


def resources(proc: Path = PROC, mounts=None, statvfs=os.statvfs) -> dict:
    mem = meminfo(proc)
    used_mem = 100.0 * (1 - mem["MemAvailable"] / mem["MemTotal"]) if mem.get("MemTotal") else 0.0
    alloc, _, fmax = (proc / "sys/fs/file-nr").read_text().split()[:3]
    nthreads = sum(int(l.split()[1]) for l in _status_threads(proc))
    tmax = int((proc / "sys/kernel/threads-max").read_text())
    load1 = float((proc / "loadavg").read_text().split()[0])
    cpus = os.cpu_count() or 1
    orphans = 0
    for line in (proc / "net/sockstat").read_text().splitlines():
        if line.startswith("TCP:"):
            parts = line.split()
            orphans = int(parts[parts.index("orphan") + 1])
    r = {"memory": round(used_mem, 1),
         "file_handles": round(100.0 * int(alloc) / max(1, int(fmax)), 2),
         "processes": round(100.0 * nthreads / max(1, tmax), 2),
         "load": round(load1 / cpus, 2), "tcp_orphans": orphans, "disks": {}}
    seen = set()
    for m in mounts or MOUNTS:
        try:
            st = statvfs(m)
        except OSError:
            continue
        key = (st.f_blocks, st.f_bfree, st.f_files)
        if key in seen or not st.f_blocks:
            continue          # the same filesystem under another mount point
        seen.add(key)
        r["disks"][m] = round(100.0 * (1 - st.f_bavail / st.f_blocks), 1)
    return r


def _status_threads(proc: Path):
    for d in proc.iterdir():
        if d.name.isdigit():
            try:
                for line in (d / "status").read_text().splitlines():
                    if line.startswith("Threads:"):
                        yield line
                        break
            except OSError:
                continue


def config_snapshot(root: Path = ROOT) -> dict:
    """path -> 'sha256:...' for configuration, 'meta:mode:uid:gid' for secrets."""
    out = {}
    for pattern in CONFIG_GLOBS:
        for name in sorted(glob.glob(str(root / pattern))):
            if len(out) >= MAX_FILES:
                return out
            p = Path(name)
            rel = "/" + str(p.relative_to(root))
            try:
                st = p.lstat()
            except OSError:
                continue
            if stat.S_ISLNK(st.st_mode):
                out[rel] = "link:" + os.readlink(p)
            elif not stat.S_ISREG(st.st_mode):
                continue
            elif SECRET_RE.search(rel):
                out[rel] = f"meta:{stat.S_IMODE(st.st_mode):o}:{st.st_uid}:{st.st_gid}"
            elif st.st_size > MAX_HASH_BYTES:
                out[rel] = f"size:{st.st_size}:{int(st.st_mtime)}"
            else:
                try:
                    out[rel] = "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()[:24] + \
                        f":{stat.S_IMODE(st.st_mode):o}"
                except OSError:
                    continue
    return out


def _hex_addr(h: str) -> str:
    raw = bytes.fromhex(h)
    if len(raw) == 4:
        return str(ipaddress.IPv4Address(raw[::-1]))
    words = [raw[i:i + 4][::-1] for i in range(0, 16, 4)]
    addr = ipaddress.IPv6Address(b"".join(words))
    return str(addr.ipv4_mapped or addr)


def connections(proc: Path = PROC) -> dict:
    """Listening ports and established inbound peers from /proc/net/tcp{,6}."""
    listen, est = set(), []
    for name in ("tcp", "tcp6"):
        try:
            lines = (proc / "net" / name).read_text().splitlines()[1:]
        except OSError:
            continue
        rows = [l.split() for l in lines if len(l.split()) > 3]
        for r in rows:
            if r[3] == "0A":
                listen.add(int(r[1].split(":")[1], 16))
        for r in rows:
            if r[3] == "01":
                lport = int(r[1].split(":")[1], 16)
                rip, rport = r[2].split(":")
                if lport in listen:
                    est.append({"port": lport, "peer": _hex_addr(rip)})
    return {"listen": sorted(listen), "inbound": est}


def counters(proc: Path = PROC) -> dict:
    lines = (proc / "net/snmp").read_text().splitlines()
    out = {}
    for head, vals in zip(lines[::2], lines[1::2]):
        proto = head.split(":")[0]
        for k, v in zip(head.split()[1:], vals.split()[1:]):
            out[f"{proto}.{k}"] = int(v)
    return {"resets": out.get("Tcp.OutRsts", 0) + out.get("Udp.NoPorts", 0)}


PREAUTH = re.compile(r"Exit before auth from <([0-9a-fA-F.:]+):\d+>")
AUTHOK = re.compile(r"auth succeeded for .* from ([0-9a-fA-F.:]+):\d+")


def preauth_exits(offsets: dict, logs=None, max_read: int = 512_000) -> tuple[dict, dict]:
    """New 'Exit before auth' lines per address since the last offsets.
    Banner grabs and scanners end before auth; real logins do too sometimes
    (Nexus's ssh probes), so addresses that also logged in are not counted."""
    counts, ok, new = {}, set(), {}
    for path in logs or DROPBEAR_LOGS:
        try:
            size = os.path.getsize(path)
            start = int(offsets.get(path, size))   # first sight: start at the end
            if start > size:
                start = 0                          # the log was truncated or rotated
            with open(path, "rb") as fh:
                fh.seek(max(start, size - max_read))
                text = fh.read().decode("utf-8", "replace")
            new[path] = size
        except OSError:
            continue
        for line in text.splitlines():
            m = PREAUTH.search(line)
            if m:
                counts[m.group(1)] = counts.get(m.group(1), 0) + 1
            m = AUTHOK.search(line)
            if m:
                ok.add(m.group(1))
    return {ip: n for ip, n in counts.items() if ip not in ok}, new


def trusted(path: Path = TRUSTED_FILE) -> list:
    try:
        data = json.loads(path.read_text())
        extra = data.get("trusted", []) if isinstance(data, dict) else []
        return TRUSTED_DEFAULT + [str(x) for x in extra][:64]
    except (OSError, ValueError):
        return list(TRUSTED_DEFAULT)


def is_trusted(ip: str, nets: list) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for n in nets:
        try:
            if addr in ipaddress.ip_network(n, strict=False):
                return True
        except ValueError:
            continue
    return False


# == detect =====================================================================

PORT_NAMES = {22: "rescue SSH", 2222: "SSH", 4243: "NRP (Nexus's line)"}


def detect(prev: dict, obs: dict, now: float):
    events = []
    state = {"t": now}

    # LNX-103 resources: alarm on entering, a quiet "recovered" on leaving.
    res, alarms = obs["resources"], dict(prev.get("alarms", {}))
    checks = [(k, res[k], LIMITS[k]) for k in LIMITS] + \
             [(f"disk:{m}", v, DISK_LIMIT) for m, v in res["disks"].items()]
    for name, value, (hi, lo) in checks:
        was = alarms.get(name, False)
        now_on = value >= hi or (was and value > lo)
        if now_on and not was:
            unit = "" if name in ("load", "tcp_orphans") else "%"
            what = name.replace("disk:", "the disk at ")
            events.append(Event("resource.exhaustion", {"resource": name, "value": value},
                                f"I am running low on {what}: {value}{unit} used "
                                f"(alarm at {hi}{unit}).", priority=3, journal=True))
        elif was and not now_on:
            events.append(Event("resource.recovered", {"resource": name, "value": value},
                                f"{name.replace('disk:', 'the disk at ')} is back to normal ({value}).",
                                priority=5))
        alarms[name] = now_on
    state["alarms"] = alarms

    # LNX-71 configuration: compare with the last snapshot (none = baseline).
    cfg, old = obs["config"], prev.get("config")
    state["config"] = cfg
    if isinstance(old, dict):
        changes = []
        for p in sorted(set(cfg) | set(old)):
            if p not in old:
                changes.append((p, "added"))
            elif p not in cfg:
                changes.append((p, "removed"))
            elif cfg[p] != old[p]:
                kind = "permissions" if cfg[p].startswith("meta:") else "modified"
                changes.append((p, kind))
        if changes:
            shown = ", ".join(f"{p} ({k})" for p, k in changes[:CONFIG_SHOW])
            more = f" and {len(changes) - CONFIG_SHOW} more" if len(changes) > CONFIG_SHOW else ""
            events.append(Event("config.changed",
                                {"count": len(changes), "path": changes[0][0], "change": changes[0][1]},
                                f"My configuration changed: {shown}{more}. Fine if someone just "
                                f"installed something; otherwise worth a look.", priority=3, journal=True))

    # LNX-101 untrusted endpoints connected to my own services.
    nets = obs["trusted"]
    for c in obs["conn"]["inbound"]:
        if not is_trusted(c["peer"], nets):
            svc = PORT_NAMES.get(c["port"], f"port {c['port']}")
            events.append(Event("endpoint.untrusted", {"peer": c["peer"], "port": c["port"]},
                                f"{c['peer']} is connected to my {svc}, and it is not on my "
                                f"trusted list.", cooldown_s=600, key=f"endpoint:{c['peer']}:{c['port']}",
                                priority=3, journal=True))

    # LNX-60 probing / fingerprinting.
    for ip, n in obs["preauth"].items():
        if n >= PROBE_BEFORE_AUTH and not is_trusted(ip, nets):
            events.append(Event("probe.detected", {"peer": ip, "kind": "ssh_preauth", "count": n},
                                f"{ip} opened my SSH {n} times and left before logging in: "
                                f"that looks like someone reading my service banners.",
                                cooldown_s=600, key=f"probe:{ip}", priority=3, journal=True))
    resets, gap = obs["counters"]["resets"], now - float(prev.get("t", 0) or 0)
    last = prev.get("resets")
    if isinstance(last, int) and 0 < gap <= SAMPLE_GAP_MAX_S and resets - last >= PROBE_RESETS:
        events.append(Event("probe.detected", {"kind": "closed_ports", "count": resets - last},
                            f"My kernel refused {resets - last} connections to closed ports in "
                            f"{int(gap)} s: something may be scanning or fingerprinting me.",
                            cooldown_s=300, key="probe:closed", priority=3, journal=True))
    state["resets"] = resets
    state["dropbear_offsets"] = obs["offsets"]
    return events, state


def observe_all(prev_offsets: dict) -> dict:
    preauth, offsets = preauth_exits(prev_offsets)
    return {"resources": resources(), "config": config_snapshot(), "conn": connections(),
            "counters": counters(), "preauth": preauth, "offsets": offsets, "trusted": trusted()}


def _config_file(state_file):
    from lynx_senses_lib import state_path
    return state_path("guard", state_file).with_name("config.json")


def run(dry_run: bool = False, state_file: str | None = None, now=None, sense_mod=None,
        observer=None, journal_path=None):
    """The config snapshot (hundreds of hashes) lives in its own file, written only
    when the configuration changes, so the 30 s state flush stays tiny on flash."""
    from lynx_senses_lib import load_state, state_path
    offsets = load_state(state_path("guard", state_file)).get("dropbear_offsets", {})
    cfg_path = _config_file(state_file)
    try:
        old_cfg = json.loads(cfg_path.read_text())
    except (OSError, ValueError):
        old_cfg = None

    def detect_with_config(prev, obs, t):
        prev = dict(prev)
        prev["config"] = old_cfg
        events, state = detect(prev, obs, t)
        cfg = state.pop("config")
        state["config_files"] = len(cfg)
        if cfg != old_cfg and not dry_run:
            cfg_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = cfg_path.with_name(cfg_path.name + ".tmp")
            tmp.write_text(json.dumps(cfg, sort_keys=True))
            os.replace(tmp, cfg_path)
        return events, state

    return run_sense("security", observer or (lambda: observe_all(offsets)), detect_with_config,
                     dry_run=dry_run, state_file=state_file, now=now, sense_mod=sense_mod,
                     journal_path=journal_path, state_name="guard")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    return finish(*run(dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
