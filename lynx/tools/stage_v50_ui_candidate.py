#!/usr/bin/env python3
"""Compile the Lynx status screen on V50 without running DRM or lighting it."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "tools/lynx_drm_dmabuf_pattern.c"
IP = "192.168.100.107"
KERNEL = "5.10.149-android12-9-o-g311738fbb5a8"
INIT_SHA = "b560f233f5ecf838b5e948d0cd3685b676a84f3097adb00d2c8bfa6e5446ab1f"
REMOTE_SOURCE = "/var/lib/lynx-devroot/tmp/lynx_drm_ui_candidate.c"
REMOTE_BINARY = "/var/lib/lynx-devroot/tmp/lynx_drm_ui_candidate"
ORIGINAL_SOURCE_SHA = "ecf8e55f6fcbba97543aa391da55ee555ccac760148df7b92942f89853aa9a25"


def ssh(command, payload=None, port=2222, timeout=25):
    argv = ssh_command(IP, command)
    argv[-2:-2] = ["-p", str(port)]
    return subprocess.run(argv, input=payload, capture_output=True, timeout=timeout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--persistent", action="store_true",
                        help="build the signal-controlled status screen at separate paths")
    args = parser.parse_args()
    remote_source = ("/var/lib/lynx-devroot/tmp/lynx_drm_status_persistent.c"
                     if args.persistent else REMOTE_SOURCE)
    remote_binary = ("/var/lib/lynx-devroot/tmp/lynx_drm_status_persistent"
                     if args.persistent else REMOTE_BINARY)
    os.umask(0o077)
    out = ROOT / "logs" / f"v50-ui-stage-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "starting", "persistent": args.persistent,
              "remote_binary": remote_binary, "ui_binary_executed": False,
              "display_enabled": False, "boot_partition_writes": False,
              "steps": []}

    def step(name, command, payload=None, port=2222, timeout=25):
        result = ssh(command, payload, port, timeout)
        (out / f"{name}.stdout").write_bytes(result.stdout)
        (out / f"{name}.stderr").write_bytes(result.stderr)
        report["steps"].append({"name": name, "exit": result.returncode})
        if result.returncode:
            raise RuntimeError(f"{name} failed; inspect saved streams")
        return result.stdout.decode(errors="replace")

    try:
        source = SOURCE.read_bytes()
        source_sha = hashlib.sha256(source).hexdigest()
        if not args.persistent and source_sha != ORIGINAL_SOURCE_SHA:
            raise RuntimeError("source changed; use --persistent to preserve the proven UI binary")
        report["source_sha256"] = source_sha
        identity = step("identity", "cat /proc/sys/kernel/random/boot_id; "
                        "uname -r; sha256sum /init | cut -c1-64; "
                        "grep 'LYNX_STATIC_NOOBIA_IP' /run/lynx/boot.log | tail -1",
                        port=22).splitlines()
        if (len(identity) != 4 or identity[1] != KERNEL or identity[2] != INIT_SHA or
                "address=192.168.100.107" not in identity[3]):
            raise RuntimeError("V50 boot identity mismatch")
        report["boot_id"] = identity[0]
        health = json.loads(step("health", "/usr/local/bin/lynx-status --assert-ready"))
        if (health["boot_id"] != identity[0] or
                health["battery"]["capacity_percent"] < 25 or
                health["battery"]["temperature_mC"] >= 35000 or
                health["thermal"]["max_mC"] >= 45000):
            raise RuntimeError("Alpine health, battery, or thermal preflight failed")
        report["battery_percent"] = health["battery"]["capacity_percent"]
        step("stage_source", f"cat > {remote_source}", payload=source, timeout=40)
        step("source_hash", f'test "$(sha256sum {remote_source} | cut -c1-64)" = "{source_sha}"')
        compile_cmd = ("chroot /var/lib/lynx-devroot /usr/bin/gcc -std=c11 -O2 "
                       "-Wall -Wextra -Werror -I/usr/include/libdrm "
                       f"/tmp/{Path(remote_source).name} -ldrm "
                       f"-o /tmp/{Path(remote_binary).name}")
        step("native_compile", compile_cmd, timeout=55)
        binary_sha = step("binary_hash", f"sha256sum {remote_binary} | cut -c1-64").strip()
        if len(binary_sha) != 64:
            raise RuntimeError("compiled binary hash missing")
        report["binary_sha256"] = binary_sha
        report["state"] = "compiled-on-v50-not-run"
    except Exception as exc:
        report.update(state="stopped-or-incomplete", error=str(exc))
    report["finished_ns"] = time.time_ns()
    path = out / "result.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "result": str(path)}))
    if report["state"] == "stopped-or-incomplete":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
