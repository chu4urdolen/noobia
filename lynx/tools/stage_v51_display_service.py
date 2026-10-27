#!/usr/bin/env python3
"""Stage, but do not enable, the verified Lynx display service on Alpine."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_v47_display_bootstrap import INIT_SHAS, KERNEL, module_bytes
from lynx_v47_touch_bootstrap import MODULES as TOUCH, MODULE_DIR
from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
IP = "192.168.100.107"
MANIFEST = ROOT / "linux-port/lynx-display-modules.list"
DISPLAY_BIN = "/var/lib/lynx-devroot/tmp/lynx_drm_status_touch_idle"
DISPLAY_SHA = "1a3d21bd40f5903377b800d0bb085443c0653a8c5ff30e1abb964e5eab0e2387"
OLD_BOOTSTRAP_SHA = "492a1906b6492e71ef31235a2ab272a491ba168d5f695ce7f2766e7ff62c68c1"
OLD_SERVICE_SHA = "8e221e82e82c2527efd1b31633b35e3fe89df8d52a3fa5ebec5c1707df2c2221"


def ssh(command, payload=None, port=2222, timeout=35):
    argv = ssh_command(IP, command)
    argv[-2:-2] = ["-p", str(port)]
    return subprocess.run(argv, input=payload, capture_output=True, timeout=timeout)


def main():
    os.umask(0o077)
    out = ROOT / "logs" / f"v51-display-stage-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "starting", "boot_partition_writes": False,
              "modules_loaded": False, "service_enabled": False, "steps": []}

    def step(name, command, payload=None, port=2222, timeout=35):
        run = ssh(command, payload, port, timeout)
        (out / f"{name}.stdout").write_bytes(run.stdout)
        (out / f"{name}.stderr").write_bytes(run.stderr)
        report["steps"].append({"name": name, "exit": run.returncode})
        if run.returncode:
            raise RuntimeError(f"{name} failed; inspect saved streams")
        return run.stdout.decode(errors="replace").strip()

    def install(name, dest, data, mode="600"):
        digest = hashlib.sha256(data).hexdigest()
        existing = step(name + "_existing", f"if test -e {dest}; then sha256sum {dest} | cut -c1-64; fi")
        if existing == digest:
            return
        allowed_old = {"lynx-display-bootstrap.sh": OLD_BOOTSTRAP_SHA,
                       "openrc-lynx-display": OLD_SERVICE_SHA}
        if existing and existing != allowed_old.get(name):
            raise RuntimeError(f"{name}: existing file differs")
        temp = dest + ".new"
        step(name + "_transfer", f"set -eu; test ! -e {temp}; cat > {temp}", data, timeout=60)
        step(name + "_install", f"set -eu; test \"$(sha256sum {temp} | cut -c1-64)\" = {digest}; "
             f"chmod {mode} {temp}; mv -f {temp} {dest}; "
             f"test \"$(sha256sum {dest} | cut -c1-64)\" = {digest}")

    try:
        identity = step("rescue_identity", "cat /proc/sys/kernel/random/boot_id; "
                        "uname -r; sha256sum /init | cut -c1-64", port=22).splitlines()
        if len(identity) != 3 or identity[1:] != [KERNEL, INIT_SHAS["v50"]]:
            raise RuntimeError("not the pinned V50 rescue boot")
        boot_id = identity[0]
        report["boot_id"] = boot_id
        health = json.loads(step("alpine_health", "/usr/local/bin/lynx-status --assert-ready"))
        if health["boot_id"] != boot_id:
            raise RuntimeError("Alpine identity differs from rescue")
        if health["root_free_mib"] < 100:
            raise RuntimeError("insufficient root free space")
        manifest = [line.split() for line in MANIFEST.read_text().splitlines()]
        if len(manifest) != 16 or any(len(row) != 3 for row in manifest):
            raise RuntimeError("display manifest shape changed")
        display = module_bytes(panel_candidate=True)
        source = {name + ".ko": data for name, _, _, data in display[:-1]}
        source["panel-cold-init.ko"] = display[-1][3]
        for name, digest in TOUCH:
            data = (MODULE_DIR / (name + ".ko")).read_bytes()
            if hashlib.sha256(data).hexdigest() != digest:
                raise RuntimeError(f"{name}: stock touch module changed")
            source[name + ".ko"] = data
        if set(source) != {row[0] for row in manifest}:
            raise RuntimeError("manifest and module files differ")
        step("directories", "set -eu; mkdir -p /var/lib/lynx-display/modules /usr/local/bin /etc/init.d; "
             "chmod 700 /var/lib/lynx-display /var/lib/lynx-display/modules")
        for filename, module, digest in manifest:
            data = source[filename]
            if hashlib.sha256(data).hexdigest() != digest:
                raise RuntimeError(f"{filename}: manifest hash mismatch")
            install(module, "/var/lib/lynx-display/modules/" + filename, data)
        install("module_list", "/var/lib/lynx-display/modules.list", MANIFEST.read_bytes(), "600")
        step("display_binary_source", f"test \"$(sha256sum {DISPLAY_BIN} | cut -c1-64)\" = {DISPLAY_SHA}")
        step("display_binary_install", "set -eu; "
             "if test -e /usr/local/bin/lynx-status-display; then "
             f"test \"$(sha256sum /usr/local/bin/lynx-status-display | cut -c1-64)\" = {DISPLAY_SHA}; "
             "else cp " + DISPLAY_BIN + " /usr/local/bin/lynx-status-display; "
             "chmod 755 /usr/local/bin/lynx-status-display; fi")
        for local, dest in (("lynx-display-bootstrap.sh", "/usr/local/bin/lynx-display-bootstrap"),
                            ("openrc-lynx-display", "/etc/init.d/lynx-display")):
            install(local, dest, (ROOT / "linux-port" / local).read_bytes(), "755")
        step("check_files", "/usr/local/bin/lynx-display-bootstrap --check-files")
        step("confirm_disabled", "set -eu; test ! -e /etc/runlevels/default/lynx-display; "
             "test ! -e /run/lynx/display-auto.pid; /usr/local/bin/lynx-status --assert-ready >/dev/null")
        report["state"] = "staged-disabled-on-v50"
    except Exception as exc:
        report.update(state="failed-or-incomplete", error=str(exc))
    report["finished_ns"] = time.time_ns()
    receipt = out / "result.json"
    receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "result": str(receipt)}))
    if report["state"] != "staged-disabled-on-v50":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
