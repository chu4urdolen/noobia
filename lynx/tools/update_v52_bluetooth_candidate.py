#!/usr/bin/env python3
"""Guarded passive supervisor update after the first V52 candidate install."""

import hashlib
import json
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "tools/lynx_bluetoothd.py"
OLD_SHA = "bff12197882193cf460ac9927b291f6a064537beb1d50b9cec4e630f739bba21"
V52_SHA = "9206aafb339ad66b2d942ea5795b8f476a5eaf3a148f9cdfc76be22cb83e30bf"


def phone(command, payload=None):
    argv = ssh_command("192.168.100.107", command)
    argv[-2:-2] = ["-p", "2222"]
    result = subprocess.run(argv, input=payload, capture_output=True, timeout=15)
    if result.returncode:
        raise RuntimeError("phone command failed: " + result.stderr.decode(errors="replace")[-500:])
    return result.stdout.decode(errors="replace")


def main():
    receipt = ROOT / "logs" / f"v52-bluetooth-candidate-update-{time.time_ns()}.json"
    source = SOURCE.read_bytes()
    new_sha = hashlib.sha256(source).hexdigest()
    record = {"state": "preflight", "old_sha256": OLD_SHA, "new_sha256": new_sha,
              "service_started": False, "boot_partition_writes": False}
    try:
        current = phone("sha256sum /dev/sdc39 | cut -c1-64; "
                        "sha256sum /usr/local/bin/lynx-bluetoothd | cut -c1-64; "
                        "! rc-service lynx-bluetooth status >/dev/null 2>&1; "
                        "test ! -e /usr/local/bin/lynx-bluetoothd.before-ready-file").splitlines()
        if current != [V52_SHA, OLD_SHA]:
            raise RuntimeError("boot or installed supervisor hash changed")
        health = json.loads(phone("/usr/local/bin/lynx-status --assert-ready"))
        if health["issues"] or health["battery"]["capacity_percent"] < 40:
            raise RuntimeError("health guard failed")
        record["boot_id"] = health["boot_id"]
        phone("cat > /run/lynx-bluetoothd.new; "
              f'test "$(sha256sum /run/lynx-bluetoothd.new | cut -c1-64)" = {new_sha}; '
              "/usr/bin/python3 -m py_compile /run/lynx-bluetoothd.new; "
              "cp -p /usr/local/bin/lynx-bluetoothd "
              "/usr/local/bin/lynx-bluetoothd.before-ready-file; "
              "install -m 755 /run/lynx-bluetoothd.new /usr/local/bin/lynx-bluetoothd",
              source)
        final = phone("sha256sum /usr/local/bin/lynx-bluetoothd | cut -c1-64; "
                      "! rc-service lynx-bluetooth status >/dev/null 2>&1")
        if final.strip() != new_sha:
            raise RuntimeError("installed supervisor hash mismatch")
        after = json.loads(phone("/usr/local/bin/lynx-status --assert-ready"))
        if after["boot_id"] != record["boot_id"] or after["issues"]:
            raise RuntimeError("health changed after passive update")
        record["state"] = "passive-supervisor-updated-healthy"
    except Exception as exc:
        record.update(state="failed", error=str(exc))
    receipt.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"state": record["state"], "receipt": str(receipt),
                      "error": record.get("error")}))
    if record["state"] != "passive-supervisor-updated-healthy":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
