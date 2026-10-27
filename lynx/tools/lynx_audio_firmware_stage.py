#!/usr/bin/env python3
"""Stage matching TFA98xx container and load it with both speakers muted."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "linux-port/artifacts/stock-cph2493-August-eu-ota/wifi-reference/odm-unpacked/firmware/tfa98xx.cnt"
SHA = "d5d0f96d14b6fb0f324b162de3c3898f2caaac6ee6a5fad64cf9bc29f4e74e87"
BOOT_ID = "1a524657-04f4-4306-9458-c5ced1c2bfb0"


def main():
    os.umask(0o077)
    out = ROOT / "logs" / f"v50-audio-firmware-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "starting", "boot_partition_writes": False,
              "speaker_muted_during_firmware_load": True, "steps": []}

    def step(label, command, *, data=None, timeout=20):
        argv = ssh_command("192.168.100.107", command)
        argv[-2:-2] = ["-p", "2222"]
        p = subprocess.run(argv, input=data, capture_output=True, timeout=timeout)
        (out / f"{label}.stdout").write_bytes(p.stdout)
        (out / f"{label}.stderr").write_bytes(p.stderr)
        report["steps"].append({"name": label, "exit": p.returncode})
        if p.returncode:
            raise RuntimeError(f"{label} failed; see saved streams")
        return p.stdout.decode(errors="replace").strip()

    try:
        data = SOURCE.read_bytes()
        if hashlib.sha256(data).hexdigest() != SHA:
            raise RuntimeError("stock TFA container hash changed")
        identity = step("identity", "cat /proc/sys/kernel/random/boot_id")
        if identity != BOOT_ID:
            raise RuntimeError("phone rebooted since reviewed audio trial")
        step("preflight", "set -eu; /usr/local/bin/lynx-status --assert-ready >/dev/null; "
             "grep -q 'mt6983mt6338' /proc/asound/cards; "
             "test ! -e /lib/firmware/tfa98xx.cnt; "
             "test \"$(cat /sys/module/snd_soc_tfa98xx/parameters/fw_name)\" = ../../odm/firmware/tfa98xx.cnt; "
             "amixer -c0 cget name='TFA98XX Firmware' | grep -q ': values=0'")
        step("mute_left", "amixer -c0 cset name='Speaker_L_Mute_Switch' On")
        step("mute_right", "amixer -c0 cset name='Speaker_R_Mute_Switch' On")
        step("stage", "set -eu; cat > /lib/firmware/tfa98xx.cnt.new", data=data)
        step("install", f"set -eu; test \"$(sha256sum /lib/firmware/tfa98xx.cnt.new | cut -c1-64)\" = {SHA}; "
             "chmod 644 /lib/firmware/tfa98xx.cnt.new; "
             "mv /lib/firmware/tfa98xx.cnt.new /lib/firmware/tfa98xx.cnt; "
             f"test \"$(sha256sum /lib/firmware/tfa98xx.cnt | cut -c1-64)\" = {SHA}")
        step("firmware_name", "printf %s tfa98xx.cnt > /sys/module/snd_soc_tfa98xx/parameters/fw_name; "
             "test \"$(cat /sys/module/snd_soc_tfa98xx/parameters/fw_name)\" = tfa98xx.cnt")
        step("load_container", "/bin/busybox timeout 15 amixer -c0 cset name='TFA98XX Firmware' 1",
             timeout=20)
        report["after"] = step("after", "amixer -c0 cget name='TFA98XX Firmware'; "
                               "amixer -c0 controls | grep -E 'TFA98XX (Profile|Volume|Firmware)'; "
                               "dmesg | grep -Ei 'tfa98|request_firmware|container' | tail -50; "
                               "/usr/local/bin/lynx-status --assert-ready >/dev/null")
        report["state"] = "firmware-loaded-speakers-muted"
    except Exception as exc:
        report.update(state="failed-or-incomplete", error=str(exc))
    report["finished_ns"] = time.time_ns()
    receipt = out / "result.json"
    receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "result": str(receipt)}))
    if report["state"] != "firmware-loaded-speakers-muted":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
