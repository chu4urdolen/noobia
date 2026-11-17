#!/usr/bin/env python3
"""Store verified stock display modules on V50 Alpine without loading them."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from lynx_v47_display_bootstrap import INIT_SHAS, KERNEL, module_bytes
from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
IP = "192.168.100.107"
DEST = "/var/lib/lynx-display/modules"


def ssh(command, payload=None, *, port=2222, timeout=25):
    argv = ssh_command(IP, command)
    argv[-2:-2] = ["-p", str(port)]
    return subprocess.run(argv, input=payload, capture_output=True, timeout=timeout)


def main():
    os.umask(0o077)
    out = ROOT / "logs" / f"v50-display-modules-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"state": "starting", "destination": DEST,
              "boot_partition_writes": False, "modules_loaded": False,
              "startup_enabled": False, "steps": []}

    def step(name, command, payload=None, *, port=2222, timeout=25):
        result = ssh(command, payload, port=port, timeout=timeout)
        (out / f"{name}.stdout").write_bytes(result.stdout)
        (out / f"{name}.stderr").write_bytes(result.stderr)
        report["steps"].append({"name": name, "exit": result.returncode})
        if result.returncode:
            raise RuntimeError(f"{name} failed; inspect saved streams")
        return result.stdout.decode(errors="replace").strip()

    try:
        modules = module_bytes(False)
        total = sum(len(data) for _, _, _, data in modules)
        report["total_bytes"] = total
        identity = step("identity", "cat /proc/sys/kernel/random/boot_id; "
                        "uname -r; sha256sum /init | cut -c1-64", port=22).splitlines()
        if len(identity) != 3 or identity[1] != KERNEL or identity[2] != INIT_SHAS["v50"]:
            raise RuntimeError("V50 rescue and kernel identity changed")
        report["boot_id"] = identity[0]
        health = json.loads(step("health", "/usr/local/bin/lynx-status --assert-ready"))
        if health["boot_id"] != identity[0]:
            raise RuntimeError("Alpine boot identity changed")
        free_kb = int(step("free_space", "df -Pk /var/lib | tail -1 | awk '{print $4}'"))
        if free_kb * 1024 < total + 32 * 1024 * 1024:
            raise RuntimeError("persistent root has insufficient space")
        step("directory", f"set -eu; mkdir -p {DEST}; chmod 700 /var/lib/lynx-display {DEST}")
        for name, digest, _, data in modules:
            final = f"{DEST}/{name}.ko"
            temp = final + ".new"
            existing = step(f"{name}_existing", f"if test -e {final}; then sha256sum {final} | cut -c1-64; fi")
            if existing:
                if existing != digest:
                    raise RuntimeError(f"{name}: existing persistent module has unexpected hash")
                continue
            step(f"{name}_transfer", f"set -eu; test ! -e {temp}; cat > {temp}",
                 payload=data, timeout=45)
            step(f"{name}_install", "set -eu; "
                 f'test "$(sha256sum {temp} | cut -c1-64)" = "{digest}"; '
                 f"chmod 600 {temp}; mv {temp} {final}; "
                 f'test "$(sha256sum {final} | cut -c1-64)" = "{digest}"')
        manifest = {
            "source": "matching August CPH2493 stock vendor ramdisk",
            "kernel": KERNEL,
            "modules": {name: digest for name, digest, _, _ in modules},
            "note": "Stored only; no module loaded or startup service enabled",
        }
        manifest_bytes = (json.dumps(manifest, indent=2) + "\n").encode()
        step("manifest", f"cat > /var/lib/lynx-display/manifest.json",
             payload=manifest_bytes)
        expected = hashlib.sha256(manifest_bytes).hexdigest()
        step("manifest_verify", "set -eu; "
             f'test "$(sha256sum /var/lib/lynx-display/manifest.json | cut -c1-64)" = "{expected}"; '
             "/usr/local/bin/lynx-status --assert-ready >/dev/null")
        report["manifest_sha256"] = expected
        report["state"] = "stock-modules-staged-not-loaded"
    except Exception as exc:
        report.update(state="stopped-or-incomplete", error=str(exc))
    report["finished_ns"] = time.time_ns()
    path = out / "result.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "result": str(path)}))
    if report["state"] != "stock-modules-staged-not-loaded":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
