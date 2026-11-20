#!/usr/bin/env python3
"""Install Lynx's additive, read-only hardware status catalog tools."""

import hashlib
import io
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
import time

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
from lynx_platform_status import COMPONENTS  # noqa: E402
from lynx_wifi_v19_contact import ssh_command  # noqa: E402

HOST = "192.168.100.107"
CATALOG = "/usr/local/share/lynx/agent-tools"
NAMES = tuple("lynx_" + part + "_status" for part in COMPONENTS) + ("lynx_platform_status",)
FILES = {"lynx-platform-status": (TOOLS / "lynx_platform_status.py", "/usr/local/bin/lynx-platform-status", 0o755)}
for name in NAMES:
    for suffix, mode in ((".sh", 0o755), (".json", 0o644)):
        FILES[name + suffix] = (TOOLS / "local_calls" / (name + suffix),
                                CATALOG + "/" + name + suffix, mode)


def phone(command, data=None, timeout=25):
    argv = ssh_command(HOST, command)
    argv[-2:-2] = ["-p", "2222"]
    try:
        result = subprocess.run(argv, input=data, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Lynx SSH timed out") from exc
    if result.returncode:
        raise RuntimeError("Lynx SSH failed: " + result.stderr.decode(errors="replace")[-300:])
    return result.stdout.decode()


def main():
    local = {}
    for archive, (source, target, mode) in FILES.items():
        data = source.read_bytes()
        if archive.endswith(".json"):
            meta = json.loads(data)
            if meta.get("name") != archive[:-5] or not isinstance(meta.get("inputSchema"), dict):
                raise RuntimeError("invalid manifest " + archive)
        elif archive == "lynx-platform-status":
            compile(data, str(source), "exec")
        else:
            subprocess.run(["/bin/sh", "-n", str(source)], check=True, timeout=3)
        local[archive] = (data, target, mode)

    health = json.loads(phone("/usr/local/bin/lynx-status --assert-ready"))
    battery = health["battery"]
    if (health.get("issues") or not health["wifi"]["carrier"] or
            battery["capacity_percent"] < 25 or battery["current_mA_signed"] <= 0 or
            battery["temperature_mC"] >= 35000 or health["thermal"]["max_mC"] >= 45000):
        raise RuntimeError("power, thermal, Wi-Fi, or health guard failed")
    queue = json.loads(phone("/usr/local/bin/lynx-agent-health"))
    if queue.get("issues") or queue.get("counts", {}).get("running"):
        raise RuntimeError("agent queue unhealthy or busy")
    old_names = set(phone("python3 -c " + shlex.quote(
        "from pathlib import Path; print('\\n'.join(p.name for p in Path('" + CATALOG + "').glob('*.json')))"
    )).splitlines())
    if len(old_names) != 15:
        raise RuntimeError("unexpected existing catalog count")
    for archive, (_data, target, _mode) in local.items():
        if phone("test ! -e " + shlex.quote(target) + " && printf absent") != "absent":
            raise RuntimeError("target already exists: " + archive)

    stage = "/run/lynx-platform-status-" + str(time.time_ns())
    payload = io.BytesIO()
    checksums = []
    with tarfile.open(fileobj=payload, mode="w") as tar:
        for name, (data, _target, mode) in local.items():
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), mode
            tar.addfile(info, io.BytesIO(data))
            checksums.append(hashlib.sha256(data).hexdigest() + "  " + name)
        data = ("\n".join(checksums) + "\n").encode()
        info = tarfile.TarInfo("SHA256SUMS")
        info.size, info.mode = len(data), 0o600
        tar.addfile(info, io.BytesIO(data))
    phone("mkdir -m 700 " + stage + " && tar -xf - -C " + stage +
          " && cd " + stage + " && sha256sum -c SHA256SUMS >/dev/null" +
          " && python3 -m py_compile lynx-platform-status", payload.getvalue(), 35)

    installed = []
    try:
        # The agent rescans manifests on each call. Expose each tool only after
        # its executable and backend are in place; no daemon restart is needed.
        for name in ("lynx-platform-status",) + tuple(n + ".sh" for n in NAMES) + tuple(n + ".json" for n in NAMES):
            data, target, mode = local[name]
            candidate = target + ".platform-candidate"
            phone("install -m " + format(mode, "o") + " " +
                  shlex.quote(stage + "/" + name) + " " + shlex.quote(candidate) +
                  " && mv " + shlex.quote(candidate) + " " + shlex.quote(target))
            installed.append(target)
            actual = phone("sha256sum " + shlex.quote(target)).split()[0]
            if actual != hashlib.sha256(data).hexdigest():
                raise RuntimeError("installed checksum mismatch: " + name)
        verify = "import json,runpy; C=runpy.run_path('/usr/local/bin/lynx-agent')['Catalog']; c=C(); print(json.dumps({'count':len(c.definitions()),'all':c.run('lynx_platform_status',{}),'usb':c.run('lynx_usb_status',{})}))"
        result = json.loads(phone("python3 -c " + shlex.quote(verify), timeout=25))
        if result["count"] != 28 or not result["all"]["ok"] or not result["usb"]["ok"]:
            raise RuntimeError("live agent catalog or tool execution failed")
        all_state = json.loads(result["all"]["output"])
        if set(all_state) != set(COMPONENTS) or all_state["usb"]["validated"] or all_state["sim"]["validated"]:
            raise RuntimeError("live status semantics failed")
        after = json.loads(phone("/usr/local/bin/lynx-status --assert-ready"))
        if after["boot_id"] != health["boot_id"] or after.get("issues"):
            raise RuntimeError("Lynx boot or health changed during install")
        print(json.dumps({"state": "verified", "boot_id": after["boot_id"],
                          "tools_before": 15, "tools_after": result["count"],
                          "installed": len(installed), "battery_percent": after["battery"]["capacity_percent"],
                          "unvalidated": [name for name, entry in all_state.items() if not entry["validated"]]},
                         sort_keys=True))
    except Exception:
        # All targets were absent at preflight, so removal is a clean rollback.
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
