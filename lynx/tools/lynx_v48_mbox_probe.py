#!/usr/bin/env python3
"""Load one stock mailbox/SCMI/MMInfra supplier into RAM and inspect binding."""

import hashlib
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
MODULE_DIR = ROOT / "linux-port/artifacts/stock-cph2493-August-eu-ota/vendor-ramdisk-unpacked/lib/modules"
MODULES = {
    "mailbox": ("mtk-mbox-mailbox.ko", "77003c737e417b6f51e365faca06f9d3823222746af2561cd014b26cd5b91b46"),
    "tinysys": ("tinysys-scmi.ko", "6fa7f4469c3eaee17cb4d039dc30fe31e38bdd8c914925036ebe36861a8c04cf"),
    "mminfra": ("mtk-mminfra-debug.ko", "7c40aa8abb29927e0bfef68484946f225b2dd5a8d983f411be166827a524eaff"),
}
INIT_SHA = "b560f233f5ecf838b5e948d0cd3685b676a84f3097adb00d2c8bfa6e5446ab1f"
KERNEL = "5.10.149-android12-9-o-g311738fbb5a8"
IP = "192.168.100.7"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", choices=MODULES, default="mailbox")
    args = parser.parse_args()
    filename, digest = MODULES[args.module]
    source = MODULE_DIR / filename
    os.umask(0o077)
    out = ROOT / "logs" / f"v48-{args.module}-probe-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "starting", "module": args.module,
              "boot_partition_writes": False, "steps": []}

    def step(name, command, *, port=2222, payload=None, timeout=20):
        argv = ssh_command(IP, command)
        argv[-2:-2] = ["-p", str(port)]
        try:
            run = subprocess.run(argv, input=payload, capture_output=True, timeout=timeout)
            code, stdout, stderr = run.returncode, run.stdout, run.stderr
        except subprocess.TimeoutExpired as exc:
            code, stdout, stderr = None, exc.stdout or b"", exc.stderr or b""
        (out / f"{name}.stdout").write_bytes(stdout)
        (out / f"{name}.stderr").write_bytes(stderr)
        report["steps"].append({"name": name, "exit": code})
        if code != 0:
            raise RuntimeError(f"{name} failed or timed out")
        return stdout.decode(errors="replace").strip()

    try:
        data = source.read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise RuntimeError("stock module hash mismatch")
        vermagic = subprocess.run(["modinfo", "-F", "vermagic", str(source)],
                                 capture_output=True, text=True, check=True).stdout
        if not vermagic.startswith(KERNEL + " "):
            raise RuntimeError("stock module ABI mismatch")
        identity = step("identity", "cat /proc/sys/kernel/random/boot_id; uname -r; sha256sum /init",
                        port=22).splitlines()
        if len(identity) != 3 or identity[1] != KERNEL or not identity[2].startswith(INIT_SHA):
            raise RuntimeError("V48 identity mismatch")
        boot_id = identity[0]
        report["boot_id"] = boot_id
        health = json.loads(step("health_before", "/usr/local/bin/lynx-status --assert-ready"))
        if health["boot_id"] != boot_id or health["battery"]["capacity_percent"] < 50 or \
           health["battery"]["temperature_mC"] >= 30000 or \
           health["thermal"]["max_mC"] >= 45000:
            raise RuntimeError("boot, battery, or temperature outside trial guard")
        if args.module == "mailbox":
            before_cmd = ("set -eu; test ! -e /sys/module/mtk_mbox_mailbox; "
                          "test ! -L /sys/bus/platform/devices/1c351000.tinysys_mbox/driver; "
                          "test ! -L /sys/bus/platform/devices/firmware:scmi/driver; ")
        elif args.module == "tinysys":
            before_cmd = ("set -eu; test ! -e /sys/module/tinysys_scmi; "
                          "test -L /sys/bus/platform/devices/1c351000.tinysys_mbox/driver; "
                          "test -L /sys/bus/platform/devices/firmware:scmi/driver; ")
        else:
            before_cmd = ("set -eu; test ! -e /sys/module/mtk_mminfra_debug; "
                          "test -L /sys/bus/scmi_protocol/devices/scmi_dev.1/driver; ")
        state = step("before", before_cmd + "printf 'scmi_devices='; ls /sys/bus/scmi_protocol/devices")
        report["before"] = state
        target = "/run/lynx/" + filename
        step("stage", f"cat > {target}", payload=data, timeout=35)
        step("verify", f"test \"$(sha256sum {target} | cut -c1-64)\" = {digest}")
        step("load", f"/bin/busybox timeout 12 /sbin/insmod {target}", timeout=20)
        report["binding"] = step("binding", "set -eu; "
                                 f'test "$(cat /proc/sys/kernel/random/boot_id)" = "{boot_id}"; '
                                 "printf 'mailbox_driver='; readlink /sys/bus/platform/devices/1c351000.tinysys_mbox/driver || :; "
                                 "printf 'scmi_driver='; readlink /sys/bus/platform/devices/firmware:scmi/driver || :; "
                                 "printf 'scmi_devices='; ls /sys/bus/scmi_protocol/devices; "
                                 "printf 'mminfra_driver='; readlink /sys/bus/platform/devices/1e827000.mminfra-debug/driver || :")
        step("health_after", "/usr/local/bin/lynx-status --assert-ready")
        report["dmesg_tail"] = step("dmesg_tail", "dmesg | tail -n 150")[-3000:]
        report["state"] = args.module + "-module-loaded-host-healthy"
    except Exception as exc:
        report.update(state="stopped", error=str(exc))
    report["finished_ns"] = time.time_ns()
    path = out / "result.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(path)
    if report["state"] == "stopped":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
