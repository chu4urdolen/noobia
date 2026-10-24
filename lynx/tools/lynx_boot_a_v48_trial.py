#!/usr/bin/env python3
"""Guarded boot_a-only V48 trial with exact V47 rollback; no implicit reboot."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import time

import lynx_boot_a_v34_trial as base


ROOT = base.ROOT
PORT = ROOT / "linux-port"
OUT = PORT / "artifacts/no-charger-shutdown-v48-offline"
V48 = OUT / "nord3-no-charger-shutdown-v48-untested.img"
V47 = PORT / "artifacts/wifi-dhcp-retry-v47-offline/nord3-wifi-dhcp-retry-v47-untested.img"
V48_SHA = "ff1244698cf791546b7c03c2f510882048c91a88f9344e80d583fda388f2340d"
V47_SHA = "c969e1938b051ab03b49ad4f2260e900e9e336997d1026ca00c3a493dedde066"


def local():
    base.local("restore-v33")
    for path, digest in ((V47, V47_SHA), (V48, V48_SHA)):
        if not path.is_file() or path.stat().st_size != 67_108_864 or base.sha(path) != digest:
            raise ValueError(f"Missing or altered image: {path}")
    build = json.loads((OUT / "build-result.json").read_text())
    valid = json.loads((OUT / "validation.json").read_text())
    if (build.get("state") != "offline-v48-candidate-built" or
            valid.get("state") != "offline-v48-validation-passed" or
            build.get("image_sha256") != V48_SHA or
            valid.get("image_sha256") != V48_SHA or
            build.get("parent_v47_sha256") != V47_SHA or
            valid.get("rollback_v47_sha256") != V47_SHA):
        raise ValueError("V48 build/validation or V47 rollback receipt mismatch")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--flash-v48", action="store_true")
    mode.add_argument("--reboot-after-v48", action="store_true")
    mode.add_argument("--restore-v47", action="store_true")
    parser.add_argument("--charged-confirmed", action="store_true",
                        help="required for flash: fresh human observation of adequate charge")
    parser.add_argument("--flash-receipt", type=Path)
    args = parser.parse_args()
    local()
    commands = {
        "flash-v48": [str(base.FASTBOOT), "-s", base.SERIAL, "flash", "boot_a", str(V48)],
        "restore-v47": [str(base.FASTBOOT), "-s", base.SERIAL, "flash", "boot_a", str(V47)],
        "reboot-after-v48": [str(base.FASTBOOT), "-s", base.SERIAL, "reboot"],
    }
    if args.prepare:
        print(json.dumps({"state": "offline-ready-flash-held", "v48_sha256": V48_SHA,
                          "v47_rollback_sha256": V47_SHA, "commands": commands,
                          "phone_contacted": False, "flash_performed": False}))
        return
    action = ("flash-v48" if args.flash_v48 else
              "restore-v47" if args.restore_v47 else "reboot-after-v48")
    if args.flash_v48 and not args.charged_confirmed:
        parser.error("--flash-v48 requires fresh --charged-confirmed")
    if args.reboot_after_v48:
        if args.flash_receipt is None:
            parser.error("--reboot-after-v48 requires --flash-receipt")
        path = args.flash_receipt.resolve(strict=True)
        if not path.is_relative_to(ROOT / "logs"):
            raise ValueError("Flash receipt outside Lynx logs")
        prior = json.loads(path.read_text())
        if (prior.get("state") != "v48-flashed-no-reboot" or
                prior.get("image_sha256") != V48_SHA or
                time.time_ns() - prior.get("finished_ns", 0) > 24 * 3600 * 10**9):
            raise ValueError("Recent complete V48 flash receipt required")
    os.umask(0o077)
    out = ROOT / "logs" / f"v48-boot-a-trial-{time.time_ns()}"
    out.mkdir(mode=0o700)
    receipt = out / "result.json"
    report = {"state": "starting", "created_ns": time.time_ns(),
              "mode": action, "image_sha256": V47_SHA if args.restore_v47 else V48_SHA,
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
                              timeout=20 if args.reboot_after_v48 else 120)
        event.update(state="returned", finished_ns=time.time_ns(),
                     elapsed_seconds=time.monotonic() - event["started_monotonic"],
                     exit_code=done.returncode, output=done.stdout + done.stderr)
        save()
        if done.returncode:
            raise ValueError("Fastboot command failed; inspect exact output")
        report["state"] = ("v48-flashed-no-reboot" if args.flash_v48 else
                           "v47-restored-no-reboot" if args.restore_v47 else
                           "v48-reboot-requested")
    except Exception as exc:
        report.update(state="failed-or-incomplete", error=str(exc))
    report["finished_ns"] = time.time_ns()
    save()
    print(json.dumps({"state": report["state"], "result": str(receipt)}))
    if report["state"] == "failed-or-incomplete":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
