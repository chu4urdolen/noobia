#!/usr/bin/env python3
"""Guarded boot_a-only V50 static-IP trial with exact V49 rollback."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import time

import lynx_boot_a_v49_trial as parent
import lynx_boot_a_v34_trial as base


ROOT = base.ROOT
PORT = ROOT / "linux-port"
OUT = PORT / "artifacts/static-noobia-ip-v50-offline"
V50 = OUT / "nord3-static-noobia-ip-v50-untested.img"
V49 = parent.V49
V50_SHA = "6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59"
V49_SHA = parent.V49_SHA


def local():
    parent.local()
    if not V50.is_file() or V50.stat().st_size != 67_108_864 or base.sha(V50) != V50_SHA:
        raise ValueError("Missing or altered V50 image")
    build = json.loads((OUT / "build-result.json").read_text())
    valid = json.loads((OUT / "validation.json").read_text())
    if (build.get("state") != "offline-v50-candidate-built" or
            valid.get("state") != "offline-v50-validation-passed" or
            build.get("image_sha256") != V50_SHA or
            valid.get("v50_sha256") != V50_SHA or
            build.get("parent_v49_sha256") != V49_SHA or
            valid.get("v49_sha256") != V49_SHA or
            valid.get("static_ip") != "192.168.100.107"):
        raise ValueError("V50 build/validation or V49 rollback receipt mismatch")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--flash-v50", action="store_true")
    mode.add_argument("--reboot-after-v50", action="store_true")
    mode.add_argument("--restore-v49", action="store_true")
    parser.add_argument("--charged-confirmed", action="store_true",
                        help="required for flash: fresh charge observation")
    parser.add_argument("--flash-receipt", type=Path)
    args = parser.parse_args()
    local()
    commands = {
        "flash-v50": [str(base.FASTBOOT), "-s", base.SERIAL, "flash", "boot_a", str(V50)],
        "restore-v49": [str(base.FASTBOOT), "-s", base.SERIAL, "flash", "boot_a", str(V49)],
        "reboot-after-v50": [str(base.FASTBOOT), "-s", base.SERIAL, "reboot"],
    }
    if args.prepare:
        print(json.dumps({"state": "offline-ready-flash-held", "static_ip": "192.168.100.107",
                          "v50_sha256": V50_SHA, "v49_rollback_sha256": V49_SHA,
                          "commands": commands, "phone_contacted": False,
                          "flash_performed": False}))
        return
    action = ("flash-v50" if args.flash_v50 else
              "restore-v49" if args.restore_v49 else "reboot-after-v50")
    if args.flash_v50 and not args.charged_confirmed:
        parser.error("--flash-v50 requires --charged-confirmed")
    if args.reboot_after_v50:
        if args.flash_receipt is None:
            parser.error("--reboot-after-v50 requires --flash-receipt")
        path = args.flash_receipt.resolve(strict=True)
        if not path.is_relative_to(ROOT / "logs"):
            raise ValueError("Flash receipt outside Lynx logs")
        prior = json.loads(path.read_text())
        if (prior.get("state") != "v50-flashed-no-reboot" or
                prior.get("image_sha256") != V50_SHA or
                time.time_ns() - prior.get("finished_ns", 0) > 24 * 3600 * 10**9):
            raise ValueError("Recent complete V50 flash receipt required")
    os.umask(0o077)
    out = ROOT / "logs" / f"v50-boot-a-trial-{time.time_ns()}"
    out.mkdir(mode=0o700)
    receipt = out / "result.json"
    report = {"state": "starting", "created_ns": time.time_ns(),
              "mode": action, "image_sha256": V49_SHA if args.restore_v49 else V50_SHA,
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
        command = commands[action]
        event = {"command": command, "state": "issued", "started_ns": time.time_ns(),
                 "started_monotonic": time.monotonic()}
        report["operations"].append(event)
        report["state"] = "command-issued"
        save()
        done = subprocess.run(command, capture_output=True, text=True,
                              timeout=20 if args.reboot_after_v50 else 120)
        event.update(state="returned", finished_ns=time.time_ns(),
                     elapsed_seconds=time.monotonic() - event["started_monotonic"],
                     exit_code=done.returncode, output=done.stdout + done.stderr)
        save()
        if done.returncode:
            raise ValueError("Fastboot command failed; inspect exact output")
        report["state"] = ("v50-flashed-no-reboot" if args.flash_v50 else
                           "v49-restored-no-reboot" if args.restore_v49 else
                           "v50-reboot-requested")
    except Exception as exc:
        report.update(state="failed-or-incomplete", error=str(exc))
    report["finished_ns"] = time.time_ns()
    save()
    print(json.dumps({"state": report["state"], "result": str(receipt)}))
    if report["state"] == "failed-or-incomplete":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
