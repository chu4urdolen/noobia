#!/usr/bin/env python3
"""Guarded V52 runtime INFO correction with an on-phone rollback copy."""

import hashlib
import json
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "tools/lynx_noob_runtime.py"
OLD_SHA = "f882acfdfb57840d0c6dc1bff16628b6a5a4c4083e3146e550fbdf7d09fed75b"
BOOT_SHA = "9206aafb339ad66b2d942ea5795b8f476a5eaf3a148f9cdfc76be22cb83e30bf"
BACKUP = "/usr/local/bin/lynx-noobd.before-info-neutral"


def phone(command, payload=None, timeout=12):
    argv = ssh_command("192.168.100.107", command)
    argv[-2:-2] = ["-p", "2222"]
    return subprocess.run(argv, input=payload, capture_output=True, timeout=timeout)


def main():
    receipt = ROOT / "logs" / f"v52-noob-info-{time.time_ns()}.json"
    source = SOURCE.read_bytes()
    new_sha = hashlib.sha256(source).hexdigest()
    report = {"state": "preflight", "boot_partition_writes": False,
              "old_sha256": OLD_SHA, "new_sha256": new_sha,
              "backup": BACKUP}
    replaced = False
    try:
        preflight = phone("set -eu; sha256sum /dev/sdc39 | cut -c1-64; "
                          "sha256sum /usr/local/bin/lynx-noobd | cut -c1-64; "
                          "rc-service lynx-noobd status >/dev/null; "
                          f"test ! -e {BACKUP}")
        if preflight.returncode or preflight.stdout.decode().splitlines() != [BOOT_SHA, OLD_SHA]:
            raise RuntimeError("boot, runtime hash, or service preflight failed")
        before = json.loads(phone("/usr/local/bin/lynx-status --assert-ready").stdout)
        if before["issues"] or before["battery"]["capacity_percent"] < 40:
            raise RuntimeError("health preflight failed")
        report["boot_id"] = before["boot_id"]
        replaced = True  # SSH may time out after the remote replacement starts.
        stage = phone("cat > /run/lynx-noobd-info.new; "
                      f'test "$(sha256sum /run/lynx-noobd-info.new | cut -c1-64)" = {new_sha}; '
                      "/usr/bin/python3 -m py_compile /run/lynx-noobd-info.new; "
                      f"cp -p /usr/local/bin/lynx-noobd {BACKUP}; "
                      "install -m 755 /run/lynx-noobd-info.new /usr/local/bin/lynx-noobd; "
                      "rc-service lynx-noobd restart", source, timeout=18)
        if stage.returncode:
            raise RuntimeError("runtime restart failed")
        local = phone("/usr/bin/python3 - <<'PY'\n"
                      "import socket\n"
                      "with socket.socket(socket.AF_UNIX) as s:\n"
                      " s.settimeout(2); s.connect('/run/lynx/noobd.sock')\n"
                      " s.sendall(b'NRP/1 17 INFO\\n')\n"
                      " reply=s.recv(256)\n"
                      " assert reply == b'NRP/1 17 OK name=Lynx firmware=alpine-native protocol=1 vm=1\\n', reply\n"
                      "print('local-info-ok')\nPY")
        if local.returncode or b"local-info-ok" not in local.stdout:
            raise RuntimeError("local NRP INFO failed")
        tcp = subprocess.run(["python3", str(ROOT / "tools/lynx_noobctl.py"), "INFO"],
                             capture_output=True, text=True, timeout=8)
        if tcp.returncode or "firmware=alpine-native" not in tcp.stdout:
            raise RuntimeError("Nexus TCP INFO failed")
        after = json.loads(phone("/usr/local/bin/lynx-status --assert-ready").stdout)
        if after["boot_id"] != report["boot_id"] or after["issues"]:
            raise RuntimeError("health changed after INFO correction")
        report["state"] = "info-corrected-local-and-tcp-healthy"
    except Exception as exc:
        report.update(state="failed", error=str(exc))
        if replaced:
            try:
                restore = phone(f"test -e {BACKUP} && "
                                f"cp -p {BACKUP} /usr/local/bin/lynx-noobd && "
                                "rc-service lynx-noobd restart", timeout=18)
                report["rollback_exit"] = restore.returncode
            except (OSError, subprocess.TimeoutExpired) as rollback_exc:
                report["rollback_error"] = str(rollback_exc)
    receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "receipt": str(receipt),
                      "error": report.get("error")}))
    if report["state"] != "info-corrected-local-and-tcp-healthy":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
