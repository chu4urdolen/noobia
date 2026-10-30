#!/usr/bin/env python3
"""Guarded boot_a-only V52 Bluetooth-before-Wi-Fi trial with exact working V50 restoration."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import time

import lynx_boot_a_v50_trial as parent
import lynx_boot_a_v34_trial as base


ROOT = base.ROOT
PORT = ROOT / "linux-port"
OUT = PORT / "artifacts/bt-before-wifi-v52-offline"
V52 = OUT / "nord3-bt-before-wifi-v52-untested.img"
V50 = parent.V50
V52_SHA = "9206aafb339ad66b2d942ea5795b8f476a5eaf3a148f9cdfc76be22cb83e30bf"
V50_SHA = parent.V50_SHA


def local():
    parent.local()
    if not V52.is_file() or V52.stat().st_size != 67_108_864 or base.sha(V52) != V52_SHA:
        raise ValueError("missing or altered V52 image")
    build = json.loads((OUT / "build-result.json").read_text())
    if (build.get("state") != "offline-v52-candidate-built" or
            build.get("image_sha256") != V52_SHA or
            build.get("parent_v50_sha256") != V50_SHA or
            build.get("new_modules_sha256") != {
                "btif_drv.ko": "f81ec909db5e986b2a8e23fa1c34f3f3a027a07e2da5335fc3917b8bf9615d51",
                "bt_drv_6983.ko": "f6c99218edc8e903b2ccbaac7f9e7176cd11b6129350ff738fb64d1b9ade5296",
            }):
        raise ValueError("V52 build or V50 restoration manifest mismatch")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--flash-v52", action="store_true")
    mode.add_argument("--reboot-after-v52", action="store_true")
    mode.add_argument("--restore-v50", action="store_true")
    parser.add_argument("--charged-confirmed", action="store_true",
                        help="fresh battery/charger observation before flash")
    parser.add_argument("--flash-receipt", type=Path)
    args = parser.parse_args()
    local()
    commands = {
        "flash-v52": [str(base.FASTBOOT), "-s", base.SERIAL, "flash", "boot_a", str(V52)],
        "restore-v50": [str(base.FASTBOOT), "-s", base.SERIAL, "flash", "boot_a", str(V50)],
        "reboot-after-v52": [str(base.FASTBOOT), "-s", base.SERIAL, "reboot"],
    }
    if args.prepare:
        print(json.dumps({"state": "offline-ready-flash-held", "v52_sha256": V52_SHA,
                          "v50_rollback_sha256": V50_SHA, "commands": commands,
                          "phone_contacted": False, "flash_performed": False}))
        return
    action = ("flash-v52" if args.flash_v52 else
              "restore-v50" if args.restore_v50 else "reboot-after-v52")
    if args.flash_v52 and not args.charged_confirmed:
        parser.error("--flash-v52 requires a fresh battery/charger observation")
    if args.reboot_after_v52:
        if args.flash_receipt is None:
            parser.error("--reboot-after-v52 requires --flash-receipt")
        path = args.flash_receipt.resolve(strict=True)
        if not path.is_relative_to(ROOT / "logs"):
            raise ValueError("flash receipt outside Lynx logs")
        prior = json.loads(path.read_text())
        if (prior.get("state") != "v52-flashed-no-reboot" or
                prior.get("image_sha256") != V52_SHA or
                time.time_ns() - prior.get("finished_ns", 0) > 24 * 3600 * 10**9):
            raise ValueError("recent complete V52 flash receipt required")
    os.umask(0o077)
    out = ROOT / "logs" / f"v52-boot-a-trial-{time.time_ns()}"
    out.mkdir(mode=0o700)
    receipt = out / "result.json"
    report = {"state": "starting", "created_ns": time.time_ns(),
              "mode": action, "image_sha256": V50_SHA if args.restore_v50 else V52_SHA,
              "partition_scope": ["boot_a"], "slot_switch_allowed": False,
              "charged_confirmed": bool(args.charged_confirmed), "operations": []}

    def save():
        temp = receipt.with_suffix(".tmp")
        temp.write_text(json.dumps(report, indent=2) + "\n")
        temp.replace(receipt)

    save()
    try:
        fresh = base.preflight()
        report.update(state="fastboot-preflight-passed", preflight_receipt=fresh["report"])
        save()
        event = {"command": commands[action], "state": "issued",
                 "started_ns": time.time_ns(), "started_monotonic": time.monotonic()}
        report["operations"].append(event)
        report["state"] = "command-issued"
        save()
        done = subprocess.run(commands[action], capture_output=True, text=True,
                              timeout=20 if args.reboot_after_v52 else 120)
        event.update(state="returned", finished_ns=time.time_ns(),
                     elapsed_seconds=time.monotonic() - event["started_monotonic"],
                     exit_code=done.returncode, output=done.stdout + done.stderr)
        save()
        if done.returncode:
            raise ValueError("Fastboot command failed; inspect exact output")
        report["state"] = ("v52-flashed-no-reboot" if args.flash_v52 else
                           "v50-restored-no-reboot" if args.restore_v50 else
                           "v52-reboot-requested")
    except Exception as exc:
        report.update(state="failed-or-incomplete", error=str(exc))
    report["finished_ns"] = time.time_ns()
    save()
    print(json.dumps({"state": report["state"], "result": str(receipt)}))
    if report["state"] == "failed-or-incomplete":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
