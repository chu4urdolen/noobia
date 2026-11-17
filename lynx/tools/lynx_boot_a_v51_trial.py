#!/usr/bin/env python3
"""Guarded boot_a-only V51 DSI trial with exact working V50 restoration."""

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
OUT = PORT / "artifacts/dsi-no-lk-v51-image-offline"
V51 = OUT / "nord3-dsi-no-lk-v51-untested.img"
V50 = parent.V50
V51_SHA = "338f1280cbdc68e8896ff6b5ebb37fd79d0497280159ac35c962dd311f98847c"
V50_SHA = parent.V50_SHA


def local():
    parent.local()
    if not V51.is_file() or V51.stat().st_size != 67_108_864 or base.sha(V51) != V51_SHA:
        raise ValueError("missing or altered V51 image")
    build = json.loads((OUT / "build-result.json").read_text())
    if (build.get("state") != "offline-v51-candidate-built-not-flashed" or
            build.get("image_sha256") != V51_SHA or
            build.get("parent_v50_sha256") != V50_SHA or
            build.get("module_sha256") !=
            "d7d522ee81fcc41fe4e4f86f34857475ec3d3ae170b37184ff6420420f822dd8"):
        raise ValueError("V51 build or V50 restoration manifest mismatch")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--flash-v51", action="store_true")
    mode.add_argument("--reboot-after-v51", action="store_true")
    mode.add_argument("--restore-v50", action="store_true")
    parser.add_argument("--charged-confirmed", action="store_true",
                        help="fresh battery/charger observation before flash")
    parser.add_argument("--flash-receipt", type=Path)
    args = parser.parse_args()
    local()
    commands = {
        "flash-v51": [str(base.FASTBOOT), "-s", base.SERIAL, "flash", "boot_a", str(V51)],
        "restore-v50": [str(base.FASTBOOT), "-s", base.SERIAL, "flash", "boot_a", str(V50)],
        "reboot-after-v51": [str(base.FASTBOOT), "-s", base.SERIAL, "reboot"],
    }
    if args.prepare:
        print(json.dumps({"state": "offline-ready-flash-held", "v51_sha256": V51_SHA,
                          "v50_rollback_sha256": V50_SHA, "commands": commands,
                          "phone_contacted": False, "flash_performed": False}))
        return
    action = ("flash-v51" if args.flash_v51 else
              "restore-v50" if args.restore_v50 else "reboot-after-v51")
    if args.flash_v51 and not args.charged_confirmed:
        parser.error("--flash-v51 requires a fresh battery/charger observation")
    if args.reboot_after_v51:
        if args.flash_receipt is None:
            parser.error("--reboot-after-v51 requires --flash-receipt")
        path = args.flash_receipt.resolve(strict=True)
        if not path.is_relative_to(ROOT / "logs"):
            raise ValueError("flash receipt outside Lynx logs")
        prior = json.loads(path.read_text())
        if (prior.get("state") != "v51-flashed-no-reboot" or
                prior.get("image_sha256") != V51_SHA or
                time.time_ns() - prior.get("finished_ns", 0) > 24 * 3600 * 10**9):
            raise ValueError("recent complete V51 flash receipt required")
    os.umask(0o077)
    out = ROOT / "logs" / f"v51-boot-a-trial-{time.time_ns()}"
    out.mkdir(mode=0o700)
    receipt = out / "result.json"
    report = {"state": "starting", "created_ns": time.time_ns(),
              "mode": action, "image_sha256": V50_SHA if args.restore_v50 else V51_SHA,
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
                              timeout=20 if args.reboot_after_v51 else 120)
        event.update(state="returned", finished_ns=time.time_ns(),
                     elapsed_seconds=time.monotonic() - event["started_monotonic"],
                     exit_code=done.returncode, output=done.stdout + done.stderr)
        save()
        if done.returncode:
            raise ValueError("Fastboot command failed; inspect exact output")
        report["state"] = ("v51-flashed-no-reboot" if args.flash_v51 else
                           "v50-restored-no-reboot" if args.restore_v50 else
                           "v51-reboot-requested")
    except Exception as exc:
        report.update(state="failed-or-incomplete", error=str(exc))
    report["finished_ns"] = time.time_ns()
    save()
    print(json.dumps({"state": report["state"], "result": str(receipt)}))
    if report["state"] == "failed-or-incomplete":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
