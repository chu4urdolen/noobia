#!/usr/bin/env python3
"""Read Lynx's factory Bluetooth address with a no-replay read-only mount."""

import json
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
REMOTE = r'''set -eu
grep -qx 'PARTNAME=nvdata' /sys/class/block/sdc10/uevent
test "$(od -An -tx1 -j 1080 -N 2 /dev/sdc10 | tr -d ' \n')" = 53ef
d=/run/lynx-nvdata-readonly
mkdir -m 700 "$d"
trap 'umount "$d" 2>/dev/null || true; rmdir "$d" 2>/dev/null || true' EXIT
mount -t ext4 -o ro,noload,nosuid,nodev,noexec /dev/sdc10 "$d"
test -f "$d/APCFG/APRDEB/BT_Addr"
od -An -tx1 -N 6 "$d/APCFG/APRDEB/BT_Addr" | tr -d ' \n'
'''


def main():
    command = ssh_command("192.168.100.107", REMOTE)
    command[-2:-2] = ["-p", "2222"]
    result = subprocess.run(command, capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise SystemExit("read-only factory address check failed: " + result.stderr[-500:])
    raw = result.stdout.strip()
    if len(raw) != 12 or any(c not in "0123456789abcdef" for c in raw):
        raise SystemExit("unexpected factory address data")
    address = ":".join(raw[i:i + 2] for i in range(0, 12, 2)).upper()
    receipt = ROOT / "logs" / f"v52-bt-factory-address-{time.time_ns()}.json"
    receipt.write_text(json.dumps({"address": address, "partition": "nvdata",
        "mount_options": "ro,noload,nosuid,nodev,noexec", "mounted_at_end": False,
        "partition_writes": False}, indent=2) + "\n")
    receipt.chmod(0o600)
    print(json.dumps({"state": "read-only-complete", "receipt": str(receipt),
                      "address_prefix": address[:8] + ":xx:xx:xx"}))


if __name__ == "__main__":
    main()
