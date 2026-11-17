#!/usr/bin/env python3
"""Guarded V52 Nexus-only remote NRP issuer update; preserves local root socket."""

import hashlib
import json
from pathlib import Path
import socket
import subprocess
import time

from lynx_ble_auth import load_key
from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
KEY = ROOT / "private/nrp-nexus.key"
BOOT_SHA = "9206aafb339ad66b2d942ea5795b8f476a5eaf3a148f9cdfc76be22cb83e30bf"
EXISTING = {
    "/usr/local/bin/lynx-noobd": "8a1eadc39c627691f7066aeecc42ba4a4fd258d98054679078066d48f35e2364",
    "/etc/init.d/lynx-noobd": "0584c102c195ff7ae9142487e2a3904db0be43e67414b5e469b2a920017572b4",
    "/usr/local/bin/lynx-ble-gatt": "549d2486ffa901c3a68b1d78bfa3ad92ec4cba616c6dd18878960bc56df15eec",
}
SOURCES = {
    "/usr/local/bin/lynx-noobd": TOOLS / "lynx_noob_runtime.py",
    "/etc/init.d/lynx-noobd": TOOLS / "lynx-noobd-local-openrc.sh",
    "/usr/local/bin/lynx-ble-gatt": TOOLS / "lynx_ble_gatt_probe.py",
    "/usr/local/bin/lynx_ble_auth.py": TOOLS / "lynx_ble_auth.py",
}
STAGED_NAMES = {
    "/usr/local/bin/lynx-noobd": "runtime.py",
    "/etc/init.d/lynx-noobd": "openrc.sh",
    "/usr/local/bin/lynx-ble-gatt": "gatt.py",
    "/usr/local/bin/lynx_ble_auth.py": "auth.py",
}


def phone(command, payload=None, timeout=16):
    argv = ssh_command("192.168.100.107", command)
    argv[-2:-2] = ["-p", "2222"]
    return subprocess.run(argv, input=payload, capture_output=True, timeout=timeout)


def nexus_command(command):
    result = subprocess.run(["python3", str(TOOLS / "lynx_noobctl.py"), command],
                            capture_output=True, text=True, timeout=12)
    if result.returncode or not result.stdout.startswith("NRP/1 1 OK"):
        raise RuntimeError("Nexus authenticated " + command + " failed")
    return result.stdout.strip()


def unsigned_rejected():
    with socket.create_connection(("192.168.100.107", 4243), timeout=4) as conn:
        conn.settimeout(4)
        with conn.makefile("rb") as stream:
            challenge = stream.readline(128)
            if not challenge.startswith(b"AUTH/1 CHALLENGE "):
                return False
            conn.sendall(b"NRP/1 97 STATUS\n")
            return stream.readline(128) == b""


def main():
    if len(load_key(KEY)) != 32:
        raise RuntimeError("Nexus key unavailable")
    out = ROOT / "logs" / f"v52-nexus-issuer-{time.time_ns()}"
    out.mkdir(mode=0o700)
    remote = "/run/lynx-nexus-issuer-" + str(time.time_ns())
    report = {"state": "preflight", "boot_partition_writes": False,
              "bluetooth_started": False, "remote": remote, "steps": []}
    modified = False

    def save():
        temporary = out / "result.tmp"
        temporary.write_text(json.dumps(report, indent=2) + "\n")
        temporary.replace(out / "result.json")

    def step(name, command, payload=None, timeout=16):
        start = time.monotonic_ns()
        try:
            result = phone(command, payload, timeout)
        except subprocess.TimeoutExpired as exc:
            (out / (name + ".stdout")).write_bytes(exc.stdout or b"")
            (out / (name + ".stderr")).write_bytes(exc.stderr or b"")
            report["steps"].append({"name": name, "timeout": True,
                                    "started_monotonic_ns": start,
                                    "ended_monotonic_ns": time.monotonic_ns()})
            save()
            raise RuntimeError(name + " timed out") from None
        (out / (name + ".stdout")).write_bytes(result.stdout)
        (out / (name + ".stderr")).write_bytes(result.stderr)
        report["steps"].append({"name": name, "exit": result.returncode,
                                "started_monotonic_ns": start,
                                "ended_monotonic_ns": time.monotonic_ns()})
        save()
        if result.returncode:
            raise RuntimeError(name + " failed")
        return result.stdout.decode(errors="replace")

    save()
    try:
        identity = step("identity", "cat /proc/sys/kernel/random/boot_id; "
                        "sha256sum /dev/sdc39 | cut -c1-64").splitlines()
        if len(identity) != 2 or identity[1] != BOOT_SHA:
            raise RuntimeError("Lynx boot_a is not exact V52")
        report["boot_id"] = identity[0]
        health = json.loads(step("health_before", "/usr/local/bin/lynx-status --assert-ready"))
        if health["issues"] or health["battery"]["capacity_percent"] < 50 or \
                health["thermal"]["max_mC"] >= 45000:
            raise RuntimeError("Lynx power or health guard failed")
        step("active_preflight", "set -eu; rc-service lynx-noobd status; "
             "! rc-service lynx-bluetooth status >/dev/null 2>&1; "
             "test -S /run/lynx/noobd.sock; "
             "test ! -e /etc/lynx/nrp-nexus.key; "
             "test ! -e /usr/local/bin/lynx_ble_auth.py; "
             "for p in /usr/local/bin/lynx-noobd /etc/init.d/lynx-noobd "
             "/usr/local/bin/lynx-ble-gatt; do "
             "test ! -e \"$p.before-nexus-auth\"; done")
        old = step("old_hashes", "sha256sum " + " ".join(EXISTING))
        observed = {line.split()[1]: line.split()[0] for line in old.splitlines()}
        if observed != EXISTING:
            raise RuntimeError("live files differ from reviewed baseline")
        step("vm_before", "set -eu; /usr/bin/python3 - <<'PY'\n"
             "import socket\n"
             "with socket.socket(socket.AF_UNIX) as s:\n"
             " s.settimeout(2); s.connect('/run/lynx/noobd.sock')\n"
             " s.sendall(b'NRP/1 1 STATUS\\n')\n"
             " answer=s.recv(256)\n"
             " assert b'state=EMPTY' in answer, answer\n"
             "print('vm-empty')\nPY")
        step("stage_dir", f"mkdir -m 700 {remote}")
        for target, source in SOURCES.items():
            name = STAGED_NAMES[target]
            payload = source.read_bytes()
            digest = hashlib.sha256(payload).hexdigest()
            check = (f"/bin/sh -n {remote}/{name}" if name == "openrc.sh" else
                     f"/usr/bin/python3 -m py_compile {remote}/{name}")
            step("stage_" + name, f"cat > {remote}/{name}; "
                 f'test "$(sha256sum {remote}/{name} | cut -c1-64)" = {digest}; '
                 + check, payload)
            report.setdefault("candidate_sha256", {})[target] = digest
        key_bytes = KEY.read_bytes()
        key_sha = hashlib.sha256(key_bytes).hexdigest()
        step("stage_key", f"cat > {remote}/nexus.key; chmod 600 {remote}/nexus.key; "
             f'test "$(sha256sum {remote}/nexus.key | cut -c1-64)" = {key_sha}',
             key_bytes)
        step("backup", "set -eu; " + " ".join(
            f"cp -p {target} {target}.before-nexus-auth;" for target in EXISTING))
        modified = True
        step("install", "set -eu; mkdir -p -m 700 /etc/lynx; "
             f"install -m 600 {remote}/nexus.key /etc/lynx/nrp-nexus.key; "
             f"install -m 644 {remote}/auth.py /usr/local/bin/lynx_ble_auth.py; "
             f"install -m 755 {remote}/runtime.py /usr/local/bin/lynx-noobd; "
             f"install -m 755 {remote}/openrc.sh /etc/init.d/lynx-noobd; "
             f"install -m 755 {remote}/gatt.py /usr/local/bin/lynx-ble-gatt; "
             "rc-service lynx-noobd restart", timeout=22)
        step("service_after", "set -eu; rc-service lynx-noobd status; "
             "test -S /run/lynx/noobd.sock; "
             "! rc-service lynx-bluetooth status >/dev/null 2>&1")
        installed = step("installed_hashes", "sha256sum " + " ".join(SOURCES))
        installed_hashes = {line.split()[1]: line.split()[0] for line in installed.splitlines()}
        if installed_hashes != report["candidate_sha256"]:
            raise RuntimeError("installed source hashes differ from reviewed candidates")
        step("key_permissions", "/usr/bin/python3 - <<'PY'\n"
             "import os, stat\n"
             "p='/etc/lynx/nrp-nexus.key'; s=os.stat(p)\n"
             "assert s.st_uid == 0 and stat.S_IMODE(s.st_mode) == 0o600\n"
             "assert len(open(p,'rb').read()) == 32\n"
             "print('key-private')\nPY")
        report["nexus_ping"] = nexus_command("PING")
        report["nexus_info"] = nexus_command("INFO")
        report["nexus_status"] = nexus_command("STATUS")
        if "state=EMPTY" not in report["nexus_status"] or not unsigned_rejected():
            raise RuntimeError("unsigned TCP was accepted or VM changed")
        report["unsigned_tcp_rejected"] = True
        after = json.loads(step("health_after", "/usr/local/bin/lynx-status --assert-ready"))
        if after["boot_id"] != identity[0] or after["issues"]:
            raise RuntimeError("Alpine health changed during issuer update")
        report["state"] = "nexus-authenticated-wifi-local-healthy"
    except Exception as exc:
        report.update(state="failed", error=str(exc))
        if modified:
            try:
                restore = phone("set -eu; " + " ".join(
                    f"cp -p {target}.before-nexus-auth {target};" for target in EXISTING) +
                    "rc-service lynx-noobd restart", timeout=22)
                report["rollback_exit"] = restore.returncode
            except (OSError, subprocess.TimeoutExpired) as rollback_exc:
                report["rollback_error"] = str(rollback_exc)
    finally:
        save()
    print(json.dumps({"state": report["state"], "receipt": str(out / "result.json"),
                      "error": report.get("error")}))
    if report["state"] != "nexus-authenticated-wifi-local-healthy":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
