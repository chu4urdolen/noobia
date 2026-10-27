#!/usr/bin/env python3
"""Stage Lynx portraits, controls, and disabled service without lighting display."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_v47_display_bootstrap import INIT_SHAS, KERNEL
from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
PICS = ROOT / "pics/frames"
REMOTE = "/var/lib/lynx-display/frames"
PORTRAIT_BIN = "/var/lib/lynx-devroot/tmp/lynx_drm_portrait_candidate"
PORTRAIT_SHA = "9aa4014a44366e6676d8493c65e0178cf4a6cb358e341d5a2d2302d8b3683c3d"
OLD_PORTRAIT_SHA = "1955134790a78f0f4e73d68affd28d7388edffb14ec8a4773759adf71e046709"
OLD_BOOTSTRAP = "07057d2b890e3731e93ded1f0695d6ac4c5b67ebd2145a4e290ae10316f73758"
INTERMEDIATE_BOOTSTRAP = "9a4aaa1baadf4ceee0665f0ad25e8c246662b4a40c454754091fe9dd9f3856f8"
LATEST_BOOTSTRAP = "c0db29966635407c9f92439868bfe2da6e14bc8abbe3a896659528817d278d43"
OLD_SERVICE = "8904db1154ec0bb9298fb27c79bb889c6f71d73e44163776fc5710d72fe8e11c"
INTERMEDIATE_SERVICE = "029320ee9e1feca3eb8f6444fb4b400f13ee1302537830c34a1597787d108d57"


def ssh(command, payload=None, port=2222, timeout=35):
    argv = ssh_command("192.168.100.107", command)
    argv[-2:-2] = ["-p", str(port)]
    return subprocess.run(argv, input=payload, capture_output=True, timeout=timeout)


def main():
    os.umask(0o077)
    out = ROOT / "logs" / f"portrait-stage-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "starting", "boot_partition_writes": False,
              "display_enabled": False, "service_enabled": False, "steps": []}

    def step(label, command, payload=None, port=2222, timeout=35):
        run = ssh(command, payload, port, timeout)
        (out / f"{label}.stdout").write_bytes(run.stdout)
        (out / f"{label}.stderr").write_bytes(run.stderr)
        report["steps"].append({"name": label, "exit": run.returncode})
        if run.returncode:
            raise RuntimeError(f"{label} failed; inspect saved streams")
        return run.stdout.decode(errors="replace").strip()

    def install(label, path, data, mode="600", previous=None):
        digest = hashlib.sha256(data).hexdigest()
        current = step(label + "_existing", f"if test -e {path}; then sha256sum {path} | cut -c1-64; fi")
        if current == digest:
            return
        permitted = set(previous) if isinstance(previous, (tuple, list)) else {previous}
        if current and current not in permitted:
            raise RuntimeError(f"{label}: existing file has an unexpected hash")
        temp = path + ".new"
        step(label + "_stage", f"set -eu; test ! -e {temp}; cat > {temp}", data, timeout=55)
        step(label + "_install", f"set -eu; test \"$(sha256sum {temp} | cut -c1-64)\" = {digest}; "
             f"chmod {mode} {temp}; mv -f {temp} {path}; "
             f"test \"$(sha256sum {path} | cut -c1-64)\" = {digest}")

    try:
        identity = step("rescue_identity", "cat /proc/sys/kernel/random/boot_id; "
                        "uname -r; sha256sum /init | cut -c1-64", port=22).splitlines()
        if len(identity) != 3 or identity[1:] != [KERNEL, INIT_SHAS["v50"]]:
            raise RuntimeError("not the pinned V50 rescue boot")
        health = json.loads(step("alpine_health", "/usr/local/bin/lynx-status --assert-ready"))
        if health["boot_id"] != identity[0] or health["root_free_mib"] < 100:
            raise RuntimeError("Alpine identity, health, or free space mismatch")
        report["boot_id"] = identity[0]
        manifest_bytes = (PICS / "manifest.json").read_bytes()
        manifest = json.loads(manifest_bytes)
        records = manifest["frames"]
        if len(records) != 17 or len(manifest["animations"]["dance"]["frames"]) != 11:
            raise RuntimeError("portrait manifest shape changed")
        if any("180deg" in item["name"] for item in records):
            raise RuntimeError("corrupted dance angle included")
        total = sum(item["bytes"] for item in records)
        if health["root_free_mib"] * 1048576 < total + 64 * 1048576:
            raise RuntimeError("persistent root has insufficient space")
        step("directory", f"set -eu; mkdir -p {REMOTE}; chmod 700 {REMOTE}")
        checksum_lines = []
        for i, item in enumerate(records):
            filename, digest = item["file"], item["sha256"]
            if not filename.endswith(".rgb565.gz") or "/" in filename:
                raise RuntimeError("invalid frame filename")
            data = (PICS / filename).read_bytes()
            if len(data) != item["bytes"] or hashlib.sha256(data).hexdigest() != digest:
                raise RuntimeError(f"frame changed: {filename}")
            install(f"frame_{i:02d}", f"{REMOTE}/{filename}", data)
            checksum_lines.append(f"{digest}  {filename}\n")
        dance = (PICS / "dance.list").read_bytes()
        if dance.decode().splitlines() != manifest["animations"]["dance"]["frames"]:
            raise RuntimeError("dance frame order differs")
        install("dance_list", f"{REMOTE}/dance.list", dance)
        checksum_lines.append(f"{hashlib.sha256(dance).hexdigest()}  dance.list\n")
        install("frame_manifest", f"{REMOTE}/manifest.json", manifest_bytes)
        install("frame_checksums", "/var/lib/lynx-display/frames.sha256",
                "".join(checksum_lines).encode())
        binary_sha = step("portrait_binary_source", f"sha256sum {PORTRAIT_BIN} | cut -c1-64")
        if binary_sha != PORTRAIT_SHA:
            raise RuntimeError("native portrait binary changed")
        step("portrait_binary_install", "set -eu; "
             "current=''; if test -e /usr/local/bin/lynx-portrait-display; then "
             "current=$(sha256sum /usr/local/bin/lynx-portrait-display | cut -c1-64); fi; "
             f"case \"$current\" in ''|{OLD_PORTRAIT_SHA}|{PORTRAIT_SHA}) ;; *) exit 1;; esac; "
             f"if test \"$current\" != {PORTRAIT_SHA}; then "
             f"cp {PORTRAIT_BIN} /usr/local/bin/lynx-portrait-display.new; "
             "chmod 755 /usr/local/bin/lynx-portrait-display.new; "
             "mv -f /usr/local/bin/lynx-portrait-display.new /usr/local/bin/lynx-portrait-display; fi; "
             f"test \"$(sha256sum /usr/local/bin/lynx-portrait-display | cut -c1-64)\" = {PORTRAIT_SHA}")
        install("displayctl", "/usr/local/bin/lynx-displayctl",
                (ROOT / "tools/lynx_displayctl.py").read_bytes(), "755")
        install("bootstrap", "/usr/local/bin/lynx-display-bootstrap",
                (ROOT / "linux-port/lynx-display-bootstrap.sh").read_bytes(), "755",
                (OLD_BOOTSTRAP, INTERMEDIATE_BOOTSTRAP, LATEST_BOOTSTRAP))
        install("service", "/etc/init.d/lynx-display",
                (ROOT / "linux-port/openrc-lynx-display").read_bytes(), "755",
                (OLD_SERVICE, INTERMEDIATE_SERVICE))
        step("files", "/usr/local/bin/lynx-display-bootstrap --check-files")
        step("list", "/usr/local/bin/lynx-displayctl list")
        step("disabled", "set -eu; test ! -e /etc/runlevels/default/lynx-display; "
             "test ! -e /run/lynx/display-auto.pid; /usr/local/bin/lynx-status --assert-ready >/dev/null")
        report["state"] = "portrait-control-staged-disabled"
        report["frame_count"] = 17
        report["dance_frames"] = 11
    except Exception as exc:
        report.update(state="failed-or-incomplete", error=str(exc))
    report["finished_ns"] = time.time_ns()
    receipt = out / "result.json"
    receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "result": str(receipt)}))
    if report["state"] != "portrait-control-staged-disabled":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
