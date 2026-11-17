#!/usr/bin/env python3
"""Install Nexus's Europe/Sofia TZif file on Lynx's persistent Alpine root."""

import hashlib
import json
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
ZONE = Path("/usr/share/zoneinfo/Europe/Sofia")
V52_SHA = "9206aafb339ad66b2d942ea5795b8f476a5eaf3a148f9cdfc76be22cb83e30bf"


def main():
    data = ZONE.read_bytes()
    if not data.startswith(b"TZif") or len(data) > 8192:
        raise RuntimeError("invalid host Sofia timezone file")
    digest = hashlib.sha256(data).hexdigest()
    remote = """set -eu
test "$(sha256sum /dev/sdc39 | cut -c1-64)" = BOOT_HASH
test ! -e /etc/localtime && test ! -L /etc/localtime
mkdir -p /usr/share/zoneinfo/Europe
cat > /usr/share/zoneinfo/Europe/Sofia.tmp
test "$(sha256sum /usr/share/zoneinfo/Europe/Sofia.tmp | cut -c1-64)" = ZONE_HASH
mv /usr/share/zoneinfo/Europe/Sofia.tmp /usr/share/zoneinfo/Europe/Sofia
ln -s /usr/share/zoneinfo/Europe/Sofia /etc/localtime
printf 'Europe/Sofia\\n' > /etc/timezone
test "$(readlink /etc/localtime)" = /usr/share/zoneinfo/Europe/Sofia
test "$(cat /etc/timezone)" = Europe/Sofia
date '+%Y-%m-%d %H:%M:%S %Z %z'
""".replace("BOOT_HASH", V52_SHA).replace("ZONE_HASH", digest)
    argv = ssh_command("192.168.100.107", remote)
    argv[-2:-2] = ["-p", "2222"]
    result = subprocess.run(argv, input=data, capture_output=True, timeout=20)
    out = ROOT / "logs" / f"sofia-timezone-install-{time.time_ns()}"
    out.mkdir(mode=0o700)
    (out / "stdout").write_bytes(result.stdout)
    (out / "stderr").write_bytes(result.stderr)
    report = {"state": "installed" if result.returncode == 0 else "failed",
              "zone": "Europe/Sofia", "source_sha256": digest,
              "source_bytes": len(data), "exit": result.returncode,
              "phone_partition_writes": False, "local_time": result.stdout.decode().strip()}
    (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"],
                      "local_time": report["local_time"],
                      "receipt": str(out / "result.json")}))
    if result.returncode:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
