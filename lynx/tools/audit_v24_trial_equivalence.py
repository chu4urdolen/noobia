#!/usr/bin/env python3
"""Compare private V24 image members with a successful handset RAM trial.

Offline only: this does not contact Lynx or authorize flashing.
"""
import argparse
import gzip
import hashlib
import json
import os
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PORT = ROOT / "linux-port"
sys.path.insert(0, str(PORT))
from image_formats import read_boot_v4, read_newc  # noqa: E402
from ramdisk_codec import decompress  # noqa: E402


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trial_receipt", type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    trial = json.loads(args.trial_receipt.read_text())
    if trial.get("state") != "phone-ram-health-stage-verified" or trial.get("flash_performed"):
        raise ValueError("Receipt is not a successful no-flash handset trial")
    image_dir = PORT / "artifacts/autonomous-health-v24-offline"
    image = (image_dir / "nord3-autonomous-health-untested.img").read_bytes()
    build = json.loads((image_dir / "build-result.json").read_text())
    if digest(image) != build["image_sha256"]:
        raise ValueError("V24 image differs from its build receipt")
    boot = read_boot_v4(image)
    primary = read_newc(decompress(boot["ramdisk"]))
    recipe = json.loads((PORT / "known-good-v19/recipe.json").read_text())
    offset = recipe["payload_offset"]
    payload_bytes = int(primary["etc/lynx/payload-bytes"]["data"].strip())
    payload = image[offset:offset + payload_bytes]
    if digest(payload).encode() != primary["etc/lynx/payload-sha256"]["data"].strip():
        raise ValueError("V24 supplement fails init metadata hash")
    supplement = read_newc(gzip.decompress(payload))
    expected = {
        "usr/share/lynx/health-inputs.tar.gz": trial["local"]["archive_sha256"],
    }
    for name, details in trial["local"]["scripts"].items():
        expected["usr/libexec/lynx/" + name] = details["sha256"]
    observed = {}
    for name, expected_sha in expected.items():
        actual_sha = digest(supplement[name]["data"])
        if actual_sha != expected_sha:
            raise ValueError("V24 member differs from live trial: " + name)
        observed[name] = actual_sha
    handoff = supplement["etc/lynx/autonomous-health-handoff.sh"]["data"]
    init = primary["init"]["data"]
    if digest(handoff) != digest((PORT / "autonomous-health-handoff.sh").read_bytes()):
        raise ValueError("V24 handoff differs from reviewed source")
    if init.count(b"lynx_autonomous_health_handoff\n") != 1:
        raise ValueError("V24 init hook absent or duplicated")
    if digest(boot["kernel"]) != build["stock_kernel_sha256"]:
        raise ValueError("V24 kernel differs from its build receipt")
    report = {
        "state": "v24-members-match-successful-ram-trial",
        "created_ns": time.time_ns(),
        "trial_receipt": str(args.trial_receipt.resolve()),
        "v24_image_sha256": digest(image),
        "stock_kernel_sha256": digest(boot["kernel"]),
        "matched_members": observed,
        "handoff_sha256": digest(handoff),
        "init_sha256": digest(init),
        "phone_contacted": False,
        "flash_performed": False,
        "limitation": "V24 init/handoff and failure path remain untested on handset; safety hold remains active.",
    }
    out = PORT / "artifacts" / ("v24-trial-equivalence-" + str(report["created_ns"]))
    out.mkdir(mode=0o700)
    target = out / "result.json"
    target.write_text(json.dumps(report, indent=2) + "\n")
    target.chmod(0o600)
    print(json.dumps({"state": report["state"], "result": str(target)}))


if __name__ == "__main__":
    main()
