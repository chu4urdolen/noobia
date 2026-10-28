#!/usr/bin/env python3
"""Install the reviewed RAM-loaded sound stack as an optional Alpine service."""

import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import time

from lynx_wifi_v19_contact import ssh_command
import lynx_audio_card_probe as card


ROOT = Path(__file__).resolve().parent.parent
BOOT_SHA = "6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59"
KERNEL = "5.10.149-android12-9-o-g311738fbb5a8"
INIT_SHA = "b560f233f5ecf838b5e948d0cd3685b676a84f3097adb00d2c8bfa6e5446ab1f"
SCRIPT = ROOT / "tools/lynx-audio-bootstrap.sh"
SERVICE = b'''#!/sbin/openrc-run
description="Lynx verified MT6983 ALSA stack"

depend() {
    need lynx-display
    after lynx-haptic
}

start() {
    ebegin "Loading Lynx audio card"
    /usr/local/bin/lynx-audio-bootstrap > /var/log/lynx-audio-bootstrap.log 2>&1
    eend $?
}

stop() {
    ebegin "Muting Lynx speakers"
    if grep -q mt6983mt6338 /proc/asound/cards; then
        amixer -c0 cset name=Speaker_L_Mute_Switch On >/dev/null
        amixer -c0 cset name=Speaker_R_Mute_Switch On >/dev/null
    fi
    eend $?
}
'''


def ssh(command, data=None, timeout=30, port=2222):
    argv = ssh_command("192.168.100.107", command)
    argv[-2:-2] = ["-p", str(port)]
    return subprocess.run(argv, input=data, capture_output=True, timeout=timeout)


def bundle():
    plan = card.old.module_plan()
    if not 30 <= len(plan) <= 90:
        raise RuntimeError("unexpected audio module plan length")
    records = []
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, path, digest, data in plan:
            if name == "snd_soc_mt6338":
                path, data, digest = card.FIXED, card.FIXED.read_bytes(), card.FIXED_SHA
            if hashlib.sha256(data).hexdigest() != digest:
                raise RuntimeError(f"module checksum changed: {name}")
            vermagic = subprocess.run(["modinfo", "-F", "vermagic", str(path)],
                                     capture_output=True, text=True, check=True).stdout.strip()
            if not vermagic.startswith(KERNEL + " "):
                raise RuntimeError(f"module ABI mismatch: {name}")
            filename = f"{name}.ko"
            info = tarfile.TarInfo("modules/" + filename)
            info.size = len(data)
            info.mode = 0o600
            info.mtime = 0
            tar.addfile(info, io.BytesIO(data))
            records.append((name, digest, filename))
        manifest = "".join(f"{name} {digest} {file}\n" for name, digest, file in records).encode()
        info = tarfile.TarInfo("modules.sha256")
        info.size = len(manifest)
        info.mode = 0o600
        info.mtime = 0
        tar.addfile(info, io.BytesIO(manifest))
    return buf.getvalue(), manifest, records


def main():
    out = ROOT / "logs" / f"v50-audio-service-install-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "preflight", "boot_partition_writes": False,
              "steps": []}

    def step(name, command, data=None, timeout=30, port=2222):
        result = ssh(command, data, timeout, port)
        (out / f"{name}.stdout").write_bytes(result.stdout)
        (out / f"{name}.stderr").write_bytes(result.stderr)
        report["steps"].append({"name": name, "exit": result.returncode})
        if result.returncode:
            raise RuntimeError(f"{name} failed; see receipt")
        return result.stdout.decode(errors="replace").strip()

    try:
        identity = step("identity", "cat /proc/sys/kernel/random/boot_id; uname -r; "
                        "sha256sum /init /dev/sdc39 | cut -c1-64", port=22).splitlines()
        if len(identity) != 4 or identity[1:] != [KERNEL, INIT_SHA, BOOT_SHA]:
            raise RuntimeError("not the verified V50 boot")
        report["boot_id"] = identity[0]
        health = json.loads(step("health", "/usr/local/bin/lynx-status --assert-ready"))
        battery = health["battery"]
        if (health["boot_id"] != identity[0] or battery["capacity_percent"] < 25 or
            battery["temperature_mC"] >= 35000 or health["thermal"]["max_mC"] >= 45000 or
            (battery["capacity_percent"] < 50 and battery["current_mA_signed"] <= 0) or
            health["root_free_mib"] < 400):
            raise RuntimeError("audio installation health preflight failed")
        step("space", "test ! -e /var/lib/lynx-audio/v1; "
             "test ! -e /var/lib/lynx-audio/v1.new; "
             "test ! -e /etc/init.d/lynx-audio; "
             "test ! -e /usr/local/bin/lynx-audio-bootstrap; "
             "grep -q mt6983mt6338 /proc/asound/cards")
        archive, manifest, records = bundle()
        report["modules"] = len(records)
        report["archive_sha256"] = hashlib.sha256(archive).hexdigest()
        (out / "modules.sha256").write_bytes(manifest)
        step("stage_archive", "mkdir -p /var/lib/lynx-audio; "
             "cat > /run/lynx/audio-bundle.tar.gz", archive, 120)
        step("extract", "set -eu; "
             f'test "$(sha256sum /run/lynx/audio-bundle.tar.gz | cut -c1-64)" = {report["archive_sha256"]}; '
             "mkdir -m 700 /var/lib/lynx-audio/v1.new; "
             "tar -xz -C /var/lib/lynx-audio/v1.new -f /run/lynx/audio-bundle.tar.gz; "
             "rm /run/lynx/audio-bundle.tar.gz; "
             "cd /var/lib/lynx-audio/v1.new; "
             "while read -r name digest file; do "
             'test "$(sha256sum "modules/$file" | cut -c1-64)" = "$digest"; '
             "done < modules.sha256; "
             "mv /var/lib/lynx-audio/v1.new /var/lib/lynx-audio/v1", timeout=80)
        script = SCRIPT.read_bytes()
        step("install_bootstrap", "cat > /usr/local/bin/lynx-audio-bootstrap; "
             "chmod 755 /usr/local/bin/lynx-audio-bootstrap", script)
        step("install_service", "cat > /etc/init.d/lynx-audio; chmod 755 /etc/init.d/lynx-audio",
             SERVICE)
        step("idempotent_start", "rc-service lynx-audio start; rc-service lynx-audio status; "
             "/usr/local/bin/lynx-status --assert-ready >/dev/null")
        step("enable", "rc-update add lynx-audio default; test -L /etc/runlevels/default/lynx-audio")
        report["state"] = "installed-and-enabled-awaiting-cold-boot"
    except Exception as exc:
        report.update(state="failed-or-incomplete", error=str(exc))
    (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "receipt": str(out / "result.json"),
                      "error": report.get("error")}))
    if report["state"] != "installed-and-enabled-awaiting-cold-boot":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
