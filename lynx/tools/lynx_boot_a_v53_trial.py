#!/usr/bin/env python3
"""Guarded boot_a-only V53 calibration-settle trial with exact V50 rollback."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import time

import lynx_boot_a_v50_trial as v50
import lynx_boot_a_v34_trial as base

ROOT = base.ROOT
OUT = ROOT / "linux-port/artifacts/bt-precal-settle-v53-offline"
V53 = OUT / "nord3-bt-precal-settle-v53-untested.img"
V53_SHA = "c047455271828cf9bfa90984eea121d8ede8754f6297fc06f33f1e99fb23c75e"
V52_SHA = "9206aafb339ad66b2d942ea5795b8f476a5eaf3a148f9cdfc76be22cb83e30bf"


def local():
    v50.local()
    if not V53.is_file() or V53.stat().st_size != 67_108_864 or base.sha(V53) != V53_SHA:
        raise ValueError("exact V53 image absent or altered")
    result = json.loads((OUT / "build-result.json").read_text())
    if (result.get("state") != "offline-v53-candidate-built" or
            result.get("image_sha256") != V53_SHA or
            result.get("parent_v52_sha256") != V52_SHA or
            result.get("rollback_v50_sha256") != v50.V50_SHA or
            result.get("settle_wait_seconds") != 30 or
            result.get("changed_supplement_members") != ["etc/lynx/wifi-runtime.sh"]):
        raise ValueError("V53 build or rollback receipt mismatch")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--flash-v53", action="store_true")
    mode.add_argument("--reboot-after-v53", action="store_true")
    mode.add_argument("--restore-v50", action="store_true")
    parser.add_argument("--charged-confirmed", action="store_true")
    parser.add_argument("--flash-receipt", type=Path)
    args = parser.parse_args()
    local()
    commands = {
        "flash-v53": ["sudo", "-n", str(base.FASTBOOT), "-s", base.SERIAL,
                      "flash", "boot_a", str(V53)],
        "restore-v50": ["sudo", "-n", str(base.FASTBOOT), "-s", base.SERIAL,
                        "flash", "boot_a", str(v50.V50)],
        "reboot-after-v53": ["sudo", "-n", str(base.FASTBOOT), "-s", base.SERIAL, "reboot"],
    }
    if args.prepare:
        print(json.dumps({"state": "offline-ready-flash-held", "v53_sha256": V53_SHA,
                          "v50_rollback_sha256": v50.V50_SHA, "commands": commands,
                          "phone_contacted": False, "flash_performed": False}))
        return
    action = ("flash-v53" if args.flash_v53 else
              "restore-v50" if args.restore_v50 else "reboot-after-v53")
    if args.flash_v53 and not args.charged_confirmed:
        parser.error("V53 flash requires a fresh battery/charger observation")
    if args.reboot_after_v53:
        if args.flash_receipt is None:
            parser.error("V53 reboot requires --flash-receipt")
        path = args.flash_receipt.resolve(strict=True)
        if not path.is_relative_to(ROOT / "logs"):
            raise ValueError("flash receipt outside Lynx logs")
        prior = json.loads(path.read_text())
        if (prior.get("state") != "v53-flashed-no-reboot" or
                prior.get("image_sha256") != V53_SHA or
                time.time_ns() - prior.get("finished_ns", 0) > 24 * 3600 * 10**9):
            raise ValueError("recent complete V53 flash receipt required")
    os.umask(0o077)
    out = ROOT / "logs" / f"v53-boot-a-trial-{time.time_ns()}"
    out.mkdir(mode=0o700)
    receipt = out / "result.json"
    report = {"state": "starting", "created_ns": time.time_ns(),
              "mode": action, "image_sha256": v50.V50_SHA if args.restore_v50 else V53_SHA,
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
                              timeout=20 if args.reboot_after_v53 else 120)
        event.update(state="returned", finished_ns=time.time_ns(),
                     elapsed_seconds=time.monotonic() - event["started_monotonic"],
                     exit_code=done.returncode, output=done.stdout + done.stderr)
        save()
        if done.returncode:
            raise ValueError("Fastboot command failed; inspect exact output")
        report["state"] = ("v53-flashed-no-reboot" if args.flash_v53 else
                           "v50-restored-no-reboot" if args.restore_v50 else
                           "v53-reboot-requested")
    except Exception as exc:
        report.update(state="failed-or-incomplete", error=str(exc))
    report["finished_ns"] = time.time_ns()
    save()
    print(json.dumps({"state": report["state"], "result": str(receipt)}))
    if report["state"] == "failed-or-incomplete":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
