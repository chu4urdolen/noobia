#!/usr/bin/env python3
"""lynx-config-audit: secrets, integrity and kernel hardening, read-only (LNX-87, LNX-64, LNX-76).

Rose's backlog group G (Gwyn, 2026-11-25). Run ON Lynx (python3 stdlib only).
Changes nothing. Three sections:

* **secrets** (LNX-76): key and secret files, SSH host keys and
  authorized_keys must not be readable by other users (the inference key may be
  group-readable by `lynx-agent` after LNX-73); private logs (what she said,
  what her agent did) must not be world-readable.
* **integrity** (LNX-87): no world-writable files in her program and service
  folders (one level, no recursive search); the three files pinned by the boot
  hand-off must match their pins - if they drift, every boot is refused.
* **kernel** (LNX-64): version and the hardening sysctls that matter.

    lynx-config-audit [--text]      exit 0 = nothing "high", 1 = a high finding, 2 = failed
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

ROOT = Path(os.environ.get("LYNX_AUDIT_ROOT", "/"))

SECRETS = ["etc/lynx/nexus-inference.key", "etc/lynx/nexus-voice.key", "etc/lynx/nrp-nexus.key",
           "etc/lynx/openai.key", "etc/noobia/aigel-lynx.secret", "etc/dropbear/lynx_ed25519_host_key",
           "root/.ssh/authorized_keys"]
GROUP_READABLE_OK = {"etc/lynx/nexus-inference.key": "lynx-agent"}   # LNX-73 privilege split
PRIVATE_LOGS = ["var/log/lynx-agent.jsonl", "var/lib/noobia/lynx_thought.txt", "var/log/lynx-tool-policy.jsonl",
                "var/log/lynx-tool-broker.jsonl", "var/log/lynx/security.jsonl"]
PROGRAM_DIRS = ["usr/local/bin", "usr/local/libexec/lynx", "etc/init.d", "etc/lynx", "etc/noobia",
                "usr/local/share/lynx/agent-tools", "usr/local/lib/noobia/lynx", "usr/local/lib/noobia/security",
                "usr/local/lib/noobia/autonomy"]
# Pinned by persistent-openrc-handoff.sh in the boot image (lynx/linux-port).
PINS = {"sbin/openrc-init": "6180c8b047e41f2f5fdf581fa3e1a9835a6e2d0a4b3ceb3a60baf3f223217078",
        "lib/ld-musl-aarch64.so.1": "32377e6d71725bb019e9ff6d5e9f16b4d5156d6f2c36504191c2d6a7c4d4a44d",
        "etc/init.d/lynx-health": "53e3efaf37c7f555c09f294bc5174b39183fac9df1db9489ae0ba93bdb50db53"}
# sysctl: (good value(s), level if not, why)
SYSCTLS = {
    "kernel/kptr_restrict": ({"1", "2"}, "warn", "kernel addresses are visible to any user (helps exploits)"),
    "kernel/dmesg_restrict": ({"1"}, "warn", "any user can read the kernel log"),
    "kernel/unprivileged_bpf_disabled": ({"1", "2"}, "warn", "unprivileged eBPF is allowed (a common kernel attack surface)"),
    "kernel/randomize_va_space": ({"2"}, "high", "address-space randomisation is not full"),
    "net/ipv4/tcp_syncookies": ({"1"}, "info", "SYN cookies off or absent (SYN-flood resilience)"),
    "net/ipv4/conf/all/accept_redirects": ({"0"}, "info", "ICMP redirects accepted (route hijack on hostile networks)"),
    "net/ipv4/conf/all/rp_filter": ({"1", "2"}, "info", "reverse-path filtering off (spoofed source addresses)"),
}


def _group_name(gid: int) -> str:
    try:
        import grp
        return grp.getgrgid(gid).gr_name
    except (KeyError, ImportError):
        return str(gid)


def audit(root: Path = ROOT) -> dict:
    findings, facts = [], {}

    def finding(level, fid, text):
        findings.append({"level": level, "id": fid, "text": text})

    # -- secrets (LNX-76)
    for rel in SECRETS:
        p = root / rel
        try:
            st = p.stat()
        except OSError:
            continue
        mode = stat.S_IMODE(st.st_mode)
        facts[rel] = oct(mode)
        if mode & 0o004:
            finding("high", f"secret-world-readable:{rel}", f"/{rel} is readable by every user ({oct(mode)})")
        elif mode & 0o040 and GROUP_READABLE_OK.get(rel) != _group_name(st.st_gid):
            finding("high", f"secret-group-readable:{rel}",
                    f"/{rel} is group-readable by {_group_name(st.st_gid)} ({oct(mode)})")
        if mode & 0o022:
            finding("high", f"secret-writable:{rel}", f"/{rel} can be changed by other users ({oct(mode)})")
    for rel in PRIVATE_LOGS:
        p = root / rel
        try:
            mode = stat.S_IMODE(p.stat().st_mode)
        except OSError:
            continue
        if mode & 0o004:
            finding("warn", f"private-log-readable:{rel}", f"/{rel} (private) is readable by every user ({oct(mode)})")

    # -- integrity (LNX-87)
    for rel in PROGRAM_DIRS:
        d = root / rel
        try:
            entries = list(d.iterdir())
            dmode = stat.S_IMODE(d.stat().st_mode)
        except OSError:
            continue
        if dmode & 0o002:
            finding("high", f"dir-world-writable:{rel}", f"/{rel} is world-writable: anyone could add programs")
        for e in entries:
            try:
                st = e.lstat()
            except OSError:
                continue
            if stat.S_ISREG(st.st_mode) and st.st_mode & 0o002:
                finding("high", f"file-world-writable:{rel}/{e.name}",
                        f"/{rel}/{e.name} is world-writable: anyone could change what root runs")
            if stat.S_ISREG(st.st_mode) and st.st_mode & stat.S_ISUID and rel.startswith("usr/local"):
                finding("warn", f"setuid:{rel}/{e.name}", f"/{rel}/{e.name} is setuid")
    pins = {}
    for rel, want in PINS.items():
        try:
            got = hashlib.sha256((root / rel).read_bytes()).hexdigest()
        except OSError:
            got = None
        pins[rel] = "match" if got == want else ("missing" if got is None else "DIFFERENT")
        if got != want:
            finding("high", f"boot-pin:{rel}",
                    f"/{rel} does not match the boot hand-off pin ({pins[rel]}): the next boot would be "
                    "REFUSED (rescue: lynx/logs/rescue-20261122/restore.sh)")
    facts["boot_pins"] = pins
    finding("info", "pinned-packages",
            "musl and openrc are pinned by the boot hand-off: never let apk upgrade them "
            "(apk add --no-upgrade; check 'apk version musl openrc' before any install)")

    # -- kernel (LNX-64)
    proc = root / "proc"
    facts["kernel"] = (proc / "sys/kernel/osrelease").read_text().strip() if (proc / "sys/kernel/osrelease").exists() else "?"
    for key, (good, level, why) in SYSCTLS.items():
        p = proc / "sys" / key
        value = p.read_text().strip() if p.exists() else None
        facts[key.replace("/", ".")] = value
        if value is None:
            if level != "info":
                finding("info", f"sysctl-absent:{key}", f"{key.replace('/', '.')} is not available in this kernel")
            continue
        if value not in good:
            finding(level, f"sysctl:{key}", f"{key.replace('/', '.')}={value}: {why}")
    facts["selinux"] = "enforcing" if (root / "sys/fs/selinux/enforce").exists() and \
        (root / "sys/fs/selinux/enforce").read_text().strip() == "1" else "absent"
    high = sum(1 for f in findings if f["level"] == "high")
    return {"ok": high == 0, "findings": findings, "facts": facts,
            "note": "read-only audit; observations, not proof of an attack"}


def text_report(r: dict) -> str:
    out = [f"Lynx config audit: {'OK' if r['ok'] else 'ATTENTION'} - kernel {r['facts'].get('kernel', '?')}, "
           f"boot pins: {', '.join(f'{k.split('/')[-1]} {v}' for k, v in r['facts']['boot_pins'].items())}"]
    order = {"high": 0, "warn": 1, "info": 2}
    for f in sorted(r["findings"], key=lambda f: order[f["level"]]):
        out.append(f"  {f['level'].upper()}: {f['text']}")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--text", action="store_true")
    args = ap.parse_args(argv)
    try:
        r = audit()
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}))
        return 2
    print(text_report(r) if args.text else json.dumps(r, indent=1))
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
