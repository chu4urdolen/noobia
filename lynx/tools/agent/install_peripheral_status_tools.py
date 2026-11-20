#!/usr/bin/env python3
"""Add read-only NFC, fingerprint, and headset tools to Lynx's agent catalog."""

import hashlib
import io
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
import time

from install_platform_status_tools import phone

TOOLS = Path(__file__).resolve().parents[1]
CATALOG = "/usr/local/share/lynx/agent-tools"
NAMES = ("lynx_nfc_status", "lynx_fingerprint_status", "lynx_headset_status",
         "lynx_peripheral_status")
FILES = {"lynx-peripheral-status": (TOOLS / "lynx_peripheral_status.py",
                                    "/usr/local/bin/lynx-peripheral-status", 0o755)}
for name in NAMES:
    for suffix, mode in ((".sh", 0o755), (".json", 0o644)):
        FILES[name + suffix] = (TOOLS / "local_calls" / (name + suffix),
                                CATALOG + "/" + name + suffix, mode)


def main():
    health = json.loads(phone("/usr/local/bin/lynx-status --assert-ready"))
    battery = health["battery"]
    if (health.get("issues") or not health["wifi"]["carrier"] or
            battery["capacity_percent"] < 25 or battery["current_mA_signed"] <= 0 or
            battery["temperature_mC"] >= 35000 or health["thermal"]["max_mC"] >= 45000):
        raise RuntimeError("power, thermal, Wi-Fi, or health guard failed")
    queue = json.loads(phone("/usr/local/bin/lynx-agent-health"))
    if queue.get("issues") or queue.get("counts", {}).get("running"):
        raise RuntimeError("agent queue unhealthy or busy")
    check_count = "import runpy; print(len(runpy.run_path('/usr/local/bin/lynx-agent')['Catalog']().definitions()))"
    if int(phone("python3 -c " + shlex.quote(check_count))) != 28:
        raise RuntimeError("unexpected catalog baseline")
    local = {}
    for name, (source, target, mode) in FILES.items():
        data = source.read_bytes()
        if name.endswith(".json"):
            meta = json.loads(data)
            if meta.get("name") != name[:-5] or not isinstance(meta.get("inputSchema"), dict):
                raise RuntimeError("invalid manifest " + name)
        elif name == "lynx-peripheral-status":
            compile(data, name, "exec")
        else:
            subprocess.run(["/bin/sh", "-n", str(source)], check=True, timeout=3)
        if phone("test ! -e " + shlex.quote(target) + " && printf absent") != "absent":
            raise RuntimeError("target exists: " + target)
        local[name] = (data, target, mode)
    stage = "/run/lynx-peripheral-status-" + str(time.time_ns())
    payload = io.BytesIO()
    hashes = []
    with tarfile.open(fileobj=payload, mode="w") as tar:
        for name, (data, _target, mode) in local.items():
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), mode
            tar.addfile(info, io.BytesIO(data))
            hashes.append(hashlib.sha256(data).hexdigest() + "  " + name)
        data = ("\n".join(hashes) + "\n").encode()
        info = tarfile.TarInfo("SHA256SUMS")
        info.size, info.mode = len(data), 0o600
        tar.addfile(info, io.BytesIO(data))
    phone("mkdir -m 700 " + stage + " && tar -xf - -C " + stage +
          " && cd " + stage + " && sha256sum -c SHA256SUMS >/dev/null" +
          " && python3 -m py_compile lynx-peripheral-status", payload.getvalue(), 35)
    installed = []
    try:
        for name in ("lynx-peripheral-status",) + tuple(n + ".sh" for n in NAMES) + tuple(n + ".json" for n in NAMES):
            data, target, mode = local[name]
            candidate = target + ".peripheral-candidate"
            phone("install -m " + format(mode, "o") + " " + shlex.quote(stage + "/" + name) +
                  " " + shlex.quote(candidate) + " && mv " + shlex.quote(candidate) +
                  " " + shlex.quote(target))
            installed.append(target)
            if phone("sha256sum " + shlex.quote(target)).split()[0] != hashlib.sha256(data).hexdigest():
                raise RuntimeError("installed hash mismatch: " + name)
        verify = "import json,runpy; c=runpy.run_path('/usr/local/bin/lynx-agent')['Catalog'](); print(json.dumps({'count':len(c.definitions()),'result':c.run('lynx_peripheral_status',{})}))"
        result = json.loads(phone("python3 -c " + shlex.quote(verify)))
        if result["count"] != 32 or not result["result"]["ok"]:
            raise RuntimeError("live agent tool failed")
        state = json.loads(result["result"]["output"])
        if set(state) != {"nfc", "fingerprint", "headset"} or any(v["validated"] for v in state.values()):
            raise RuntimeError("invalid peripheral status semantics")
        after = json.loads(phone("/usr/local/bin/lynx-status --assert-ready"))
        if after["boot_id"] != health["boot_id"] or after.get("issues"):
            raise RuntimeError("boot or health changed")
        print(json.dumps({"state": "verified", "boot_id": after["boot_id"],
                          "catalog_tools": result["count"], "peripherals": state}, sort_keys=True))
    except Exception:
        if installed:
            phone("rm -f " + " ".join(shlex.quote(path) for path in installed))
        raise
    finally:
        phone("rm -rf " + shlex.quote(stage))


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None
