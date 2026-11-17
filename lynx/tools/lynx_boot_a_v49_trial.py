#!/usr/bin/env python3
"""Guarded boot_a-only V49 IOMMU trial with exact V48 rollback."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import time

import lynx_boot_a_v48_trial as parent
import lynx_boot_a_v34_trial as base


ROOT = base.ROOT
PORT = ROOT / "linux-port"
OUT = PORT / "artifacts/iommu-before-cmdq-v49-offline"
V49 = OUT / "nord3-iommu-before-cmdq-v49-untested.img"
V48 = parent.V48
V49_SHA = "896aa4937b168090cd3c75d41995917dad05aedfbc7bf83790fe31342b061e0f"
V48_SHA = parent.V48_SHA


def local():
    parent.local()
    for path, digest in ((V49, V49_SHA), (V48, V48_SHA)):
        if not path.is_file() or path.stat().st_size != 67_108_864 or base.sha(path) != digest:
            raise ValueError(f"Missing or altered image: {path}")
    build = json.loads((OUT / "build-result.json").read_text())
    valid = json.loads((OUT / "validation.json").read_text())
    if (build.get("state") != "offline-v49-candidate-built" or
            valid.get("state") != "offline-v49-validation-passed" or
            build.get("image_sha256") != V49_SHA or
            valid.get("image_sha256") != V49_SHA or
            build.get("parent_v48_sha256") != V48_SHA or
            valid.get("rollback_v48_sha256") != V48_SHA):
        raise ValueError("V49 build/validation or V48 rollback receipt mismatch")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--flash-v49", action="store_true")
    mode.add_argument("--reboot-after-v49", action="store_true")
    mode.add_argument("--restore-v48", action="store_true")
    parser.add_argument("--charged-confirmed", action="store_true",
                        help="required for flash: fresh battery observation")
    parser.add_argument("--flash-receipt", type=Path)
    args = parser.parse_args()
    local()
    commands = {
        "flash-v49": [str(base.FASTBOOT), "-s", base.SERIAL, "flash", "boot_a", str(V49)],
        "restore-v48": [str(base.FASTBOOT), "-s", base.SERIAL, "flash", "boot_a", str(V48)],
        "reboot-after-v49": [str(base.FASTBOOT), "-s", base.SERIAL, "reboot"],
    }
    if args.prepare:
        print(json.dumps({"state": "offline-ready-flash-held", "v49_sha256": V49_SHA,
                          "v48_rollback_sha256": V48_SHA, "commands": commands,
                          "phone_contacted": False, "flash_performed": False}))
        return
    action = ("flash-v49" if args.flash_v49 else
              "restore-v48" if args.restore_v48 else "reboot-after-v49")
    if args.flash_v49 and not args.charged_confirmed:
        parser.error("--flash-v49 requires --charged-confirmed")
    if args.reboot_after_v49:
        if args.flash_receipt is None:
            parser.error("--reboot-after-v49 requires --flash-receipt")
        path = args.flash_receipt.resolve(strict=True)
        if not path.is_relative_to(ROOT / "logs"):
            raise ValueError("Flash receipt outside Lynx logs")
        prior = json.loads(path.read_text())
        if (prior.get("state") != "v49-flashed-no-reboot" or
                prior.get("image_sha256") != V49_SHA or
                time.time_ns() - prior.get("finished_ns", 0) > 24 * 3600 * 10**9):
            raise ValueError("Recent complete V49 flash receipt required")
    os.umask(0o077)
    out = ROOT / "logs" / f"v49-boot-a-trial-{time.time_ns()}"
    out.mkdir(mode=0o700)
    receipt = out / "result.json"
    report = {"state": "starting", "created_ns": time.time_ns(),
              "mode": action, "image_sha256": V48_SHA if args.restore_v48 else V49_SHA,
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
                              timeout=20 if args.reboot_after_v49 else 120)
        event.update(state="returned", finished_ns=time.time_ns(),
                     elapsed_seconds=time.monotonic() - event["started_monotonic"],
                     exit_code=done.returncode, output=done.stdout + done.stderr)
        save()
        if done.returncode:
            raise ValueError("Fastboot command failed; inspect exact output")
        report["state"] = ("v49-flashed-no-reboot" if args.flash_v49 else
                           "v48-restored-no-reboot" if args.restore_v48 else
                           "v49-reboot-requested")
    except Exception as exc:
        report.update(state="failed-or-incomplete", error=str(exc))
    report["finished_ns"] = time.time_ns()
    save()
    print(json.dumps({"state": report["state"], "result": str(receipt)}))
    if report["state"] == "failed-or-incomplete":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
