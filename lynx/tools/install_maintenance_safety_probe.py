#!/usr/bin/env python3
"""Install the diagnostic-only Lynx maintenance guard update over pinned SSH.

The boot image and independent battery/thermal watchers are untouched.
"""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "linux-port/lynx-maintenance-watch.sh"
IP = "192.168.100.107"
TARGET = "/usr/libexec/lynx-maintenance-watch.sh"
BACKUP = "/root/lynx-rescue/lynx-maintenance-before-cooling-grace-v2-20261107.sh"
STAGED = "/run/lynx/lynx-maintenance-safety-probe.new"


def main():
    subprocess.run(["/bin/sh", "-n", str(SOURCE)], check=True)
    image = SOURCE.read_bytes()
    new_sha = hashlib.sha256(image).hexdigest()
    os.umask(0o077)
    out = ROOT / "logs" / f"maintenance-safety-probe-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "started", "source_sha256": new_sha,
              "boot_partition_writes": False, "steps": []}

    def step(name, command, payload=None, timeout=30):
        argv = ssh_command(IP, command)
        argv[-2:-2] = ["-p", "2222"]
        run = subprocess.run(argv, input=payload, capture_output=True, timeout=timeout)
        (out / f"{name}.stdout").write_bytes(run.stdout)
        (out / f"{name}.stderr").write_bytes(run.stderr)
        report["steps"].append({"name": name, "exit_code": run.returncode,
                                "stdout_sha256": hashlib.sha256(run.stdout).hexdigest()})
        if run.returncode:
            raise RuntimeError(f"{name} failed; inspect {out}")
        return run.stdout.decode(errors="replace")

    installed = False
    try:
        ready = json.loads(step("preflight", "/usr/local/bin/lynx-status --assert-ready"))
        boot_id = ready["boot_id"]
        if ready["battery"]["capacity_percent"] < 40 or ready["issues"]:
            raise RuntimeError("battery or health gate failed")
        old_sha = step("old-hash", f"sha256sum {TARGET} | cut -c1-64").strip()
        report.update(boot_id=boot_id, old_sha256=old_sha)
        if old_sha == new_sha:
            report["state"] = "already-installed"
            return
        step("stage", f"cat > {STAGED}", payload=image)
        step("backup", "set -eu; "
             f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}"; '
             f'test "$(sha256sum {TARGET} | cut -c1-64)" = "{old_sha}"; '
             f'test "$(sha256sum {STAGED} | cut -c1-64)" = "{new_sha}"; '
             f"test ! -e {BACKUP}; install -d -m 0700 /root/lynx-rescue; "
             f"cp -p {TARGET} {BACKUP}")
        step("install", "set -eu; "
             f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}"; '
             f'test "$(sha256sum {BACKUP} | cut -c1-64)" = "{old_sha}"; '
             f"install -m 0755 {STAGED} {TARGET}.new; mv {TARGET}.new {TARGET}; "
             "/sbin/rc-service lynx-maintenance restart; "
             "/sbin/rc-service lynx-maintenance status", timeout=40)
        installed = True
        proof = step("verify", "set -eu; "
             f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}"; '
             f'test "$(sha256sum {TARGET} | cut -c1-64)" = "{new_sha}"; '
             f'test "$(sha256sum {BACKUP} | cut -c1-64)" = "{old_sha}"; '
             "/sbin/rc-service lynx-health status >/dev/null; "
             "/sbin/rc-service lynx-battery-reserve status >/dev/null; "
             "/sbin/rc-service lynx-maintenance status >/dev/null; "
             "/usr/local/bin/lynx-status --assert-ready")
        report["verified_status"] = json.loads(proof)
        report["state"] = "installed-and-healthy"
    except Exception as error:
        report.update(state="failed", error=str(error))
        if installed:
            try:
                step("restore", "set -eu; "
                     f'test "$(sha256sum {BACKUP} | cut -c1-64)" = "{report["old_sha256"]}"; '
                     f"cp -p {BACKUP} {TARGET}.restore; mv {TARGET}.restore {TARGET}; "
                     "/sbin/rc-service lynx-maintenance restart; "
                     "/sbin/rc-service lynx-maintenance status", timeout=40)
                report["restored"] = True
            except Exception as restore_error:
                report["restore_error"] = str(restore_error)
        raise
    finally:
        report["finished_ns"] = time.time_ns()
        path = out / "result.json"
        path.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({"state": report["state"], "result": str(path)}))


if __name__ == "__main__":
    main()
