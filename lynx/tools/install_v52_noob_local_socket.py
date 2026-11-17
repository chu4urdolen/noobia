#!/usr/bin/env python3
"""Add a root-only local NRP/1 socket to V52 with exact rollback copies."""

import hashlib
import json
from pathlib import Path
import socket
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "tools/lynx_noob_runtime.py"
OPENRC = ROOT / "tools/lynx-noobd-local-openrc.sh"
BOOT = "9206aafb339ad66b2d942ea5795b8f476a5eaf3a148f9cdfc76be22cb83e30bf"
OLD_RUNTIME = "9e22d3dfabc4a225ce535b5dd61e207fdf1a16c0cfc2c01a863a3ba7a9c9db9f"
OLD_OPENRC = "41f8a98fa9e4f96f8c2eb973d24607f786a9ba4ef26bbb78f39293d632fc49f5"
REMOTE_RUNTIME = "/usr/local/bin/lynx-noobd"
REMOTE_OPENRC = "/etc/init.d/lynx-noobd"
SOCKET = "/run/lynx/noobd.sock"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def phone(command, data=None, timeout=25):
    args = ssh_command("192.168.100.107", command)
    args[-2:-2] = ["-p", "2222"]
    return subprocess.run(args, input=data, capture_output=True, timeout=timeout)


def nrp_ping():
    with socket.create_connection(("192.168.100.107", 4243), timeout=4) as conn:
        conn.settimeout(4)
        conn.sendall(b"NRP/1 173 PING\n")
        return conn.recv(256).split(b"\n", 1)[0].decode() == "NRP/1 173 OK PONG"


def main():
    out = ROOT / "logs" / f"v52-noob-local-socket-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "preflight", "boot_partition_writes": False,
              "socket": SOCKET, "steps": []}
    source_runtime = RUNTIME.read_bytes()
    source_openrc = OPENRC.read_bytes()
    runtime_sha, openrc_sha = digest(source_runtime), digest(source_openrc)
    report["candidate_sha256"] = {"runtime": runtime_sha, "openrc": openrc_sha}
    mutation_attempted = False

    def save():
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")

    def step(name, command, data=None, timeout=25):
        result = phone(command, data, timeout)
        (out / f"{name}.stdout").write_bytes(result.stdout)
        (out / f"{name}.stderr").write_bytes(result.stderr)
        report["steps"].append({"name": name, "exit": result.returncode})
        save()
        if result.returncode:
            raise RuntimeError(name + " failed")
        return result.stdout.decode(errors="replace").strip()

    save()
    try:
        baseline = step("identity", f"sha256sum /dev/sdc39 {REMOTE_RUNTIME} {REMOTE_OPENRC}").splitlines()
        if [line.split()[0] for line in baseline] != [BOOT, OLD_RUNTIME, OLD_OPENRC]:
            raise RuntimeError("V52 or live NRP baseline changed")
        if phone(f"test -e {REMOTE_RUNTIME}.before-local-socket || "
                 f"test -e {REMOTE_OPENRC}.before-local-socket").returncode == 0:
            raise RuntimeError("local-socket rollback already exists")
        health = json.loads(step("health_before", "/usr/local/bin/lynx-status --assert-ready"))
        if health["issues"] or health["battery"]["capacity_percent"] < 40:
            raise RuntimeError("Alpine health guard failed")
        report["boot_id"] = health["boot_id"]
        if not nrp_ping():
            raise RuntimeError("NRP TCP baseline failed")
        step("stage_runtime", f"set -eu; cat > /run/lynx-noobd-local.next; "
             f'test "$(sha256sum /run/lynx-noobd-local.next | cut -c1-64)" = {runtime_sha}; '
             "/usr/bin/python3 -m py_compile /run/lynx-noobd-local.next", source_runtime)
        step("stage_openrc", f"set -eu; cat > /run/lynx-noobd-openrc.next; "
             f'test "$(sha256sum /run/lynx-noobd-openrc.next | cut -c1-64)" = {openrc_sha}; '
             "/bin/sh -n /run/lynx-noobd-openrc.next", source_openrc)
        mutation_attempted = True
        step("install_restart", "set -eu; "
             f'test "$(sha256sum /dev/sdc39 | cut -c1-64)" = {BOOT}; '
             f'test "$(sha256sum {REMOTE_RUNTIME} | cut -c1-64)" = {OLD_RUNTIME}; '
             f'test "$(sha256sum {REMOTE_OPENRC} | cut -c1-64)" = {OLD_OPENRC}; '
             f"cp -p {REMOTE_RUNTIME} {REMOTE_RUNTIME}.before-local-socket; "
             f"cp -p {REMOTE_OPENRC} {REMOTE_OPENRC}.before-local-socket; "
             f"cp /run/lynx-noobd-local.next {REMOTE_RUNTIME}.next; "
             f"cp /run/lynx-noobd-openrc.next {REMOTE_OPENRC}.next; "
             f"chmod 755 {REMOTE_RUNTIME}.next {REMOTE_OPENRC}.next; "
             f"mv {REMOTE_RUNTIME}.next {REMOTE_RUNTIME}; "
             f"mv {REMOTE_OPENRC}.next {REMOTE_OPENRC}; "
             "rc-service lynx-noobd restart", timeout=40)
        proof = step("local_ping", "/usr/bin/python3 -c 'import socket,os,stat; "
             "p=\"/run/lynx/noobd.sock\"; s=os.stat(p); "
             "assert stat.S_ISSOCK(s.st_mode) and s.st_mode & 0o777 == 0o600 and s.st_uid == 0; "
             "c=socket.socket(socket.AF_UNIX); c.settimeout(3); c.connect(p); "
             "c.sendall(b\"NRP/1 174 PING\\n\"); "
             "assert c.recv(256).startswith(b\"NRP/1 174 OK PONG\"); c.close(); print(\"local PONG\")'")
        report["local_proof"] = proof
        if not nrp_ping():
            raise RuntimeError("NRP TCP PING changed")
        after = json.loads(step("health_after", "/usr/local/bin/lynx-status --assert-ready"))
        if after["boot_id"] != health["boot_id"] or after["issues"]:
            raise RuntimeError("Alpine health changed")
        step("service", "rc-service lynx-noobd status")
        report["state"] = "installed-local-and-tcp-healthy"
    except Exception as exc:
        report.update(state="failed", error=str(exc))
        if mutation_attempted:
            rollback = phone("set -eu; "
                             f"if test -f {REMOTE_RUNTIME}.before-local-socket && "
                             f"test -f {REMOTE_OPENRC}.before-local-socket; then "
                             f"cp -p {REMOTE_RUNTIME}.before-local-socket {REMOTE_RUNTIME}; "
                             f"cp -p {REMOTE_OPENRC}.before-local-socket {REMOTE_OPENRC}; "
                             "rc-service lynx-noobd restart; fi", timeout=40)
            report["rollback_exit"] = rollback.returncode
    save()
    print(json.dumps({"state": report["state"], "receipt": str(out / "result.json"),
                      "error": report.get("error")}))
    if report["state"] != "installed-local-and-tcp-healthy":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
