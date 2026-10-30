#!/usr/bin/env python3
"""Historical V50 hardware interface installer; refuse to overwrite its rollback."""

import hashlib
import json
from pathlib import Path
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
BOOT = "6168cd6288679a321a4d8bc41c7d3dde64a49d3cfe855b8e44542f3307fd5a59"
STAGE = "/run/lynx-hardware-deploy"
FILES = {
    ROOT / "tools/lynx_hardware.py": "/usr/local/bin/lynx_hardware.py",
    ROOT / "tools/lynx_microphone_level.py": "/usr/local/bin/lynx_microphone_level.py",
    ROOT / "tools/lynx_noob_runtime.py": "/usr/local/bin/lynx-noobd",
}
for local in sorted((ROOT / "tools/local_calls").iterdir()):
    FILES[local] = "/usr/local/share/lynx-tools/calls/" + local.name


def remote(command, data=None, timeout=25):
    args = ssh_command("192.168.100.107", command)
    args[-2:-2] = ["-p", "2222"]
    return subprocess.run(args, input=data, capture_output=True, timeout=timeout)


def main():
    receipt = ROOT / "logs" / f"v50-hardware-status-gnss-fix-{time.time_ns()}"
    receipt.mkdir(mode=0o700)
    report = {"state": "preflight", "boot_partition_writes": False,
              "files": {str(k): v for k, v in FILES.items()}, "steps": []}
    installed = False

    def step(name, command, data=None, timeout=25):
        result = remote(command, data, timeout)
        report["steps"].append({"name": name, "exit": result.returncode,
                                "stdout": result.stdout.decode(errors="replace")[-1200:],
                                "stderr": result.stderr.decode(errors="replace")[-700:]})
        if result.returncode:
            raise RuntimeError(f"{name} failed: {result.stderr.decode(errors='replace')[-300:]}")
        return result.stdout.decode(errors="replace").strip()

    try:
        if remote("test -e /usr/local/bin/lynx-noobd.before-hardware-status-gnss-fix").returncode == 0:
            raise RuntimeError("historical installer already applied; preserve its rollback")
        identity = step("identity", "uname -r; sha256sum /dev/sdc39 /usr/local/bin/lynx-noobd")
        lines = identity.splitlines()
        if lines[0] != "5.10.149-android12-9-o-g311738fbb5a8" or lines[1].split()[0] != BOOT:
            raise RuntimeError("not verified V50")
        old_runtime = lines[2].split()[0]
        report["old_runtime_sha256"] = old_runtime
        health = json.loads(step("health", "/usr/local/bin/lynx-status --assert-ready"))
        if (health["issues"] or health["battery"]["capacity_percent"] < 25 or
            health["battery"]["temperature_mC"] >= 35000 or
            health["thermal"]["max_mC"] >= 45000):
            raise RuntimeError("health guard failed")
        report["boot_id"] = health["boot_id"]
        step("service", "rc-service lynx-noobd status; test -S /run/lynx/media.sock")
        step("stage_dir", f"mkdir -p {STAGE}; chmod 700 {STAGE}")
        for local in FILES:
            target = f"{STAGE}/{local.name}"
            digest = hashlib.sha256(local.read_bytes()).hexdigest()
            step("stage_" + local.name, f"cat > {target}; "
                 f'test "$(sha256sum {target} | cut -c1-64)" = {digest}', local.read_bytes())
        step("syntax", f"/usr/bin/python3 -m py_compile {STAGE}/lynx_hardware.py "
             f"{STAGE}/lynx_microphone_level.py {STAGE}/lynx_noob_runtime.py; "
             f"PYTHONPATH={STAGE} /usr/bin/python3 {STAGE}/lynx_hardware.py status all >/dev/null")
        # The new module can be imported from its stage directory before the service changes.
        step("candidate", f"PYTHONPATH={STAGE} /usr/bin/python3 -c "
             "'from lynx_noob_runtime import Runtime; r=Runtime(); "
             "assert \"MIC_STATUS\" in r.dispatch(\"NRP/1 1 CAPS\"); "
             "assert \"value=0\" in r.dispatch(\"NRP/1 2 CALL MIC_STATUS\")'")
        stage_script = f"""set -eu
test "$(sha256sum /dev/sdc39 | cut -c1-64)" = {BOOT}
test "$(sha256sum /usr/local/bin/lynx-noobd | cut -c1-64)" = {old_runtime}
mkdir -p /usr/local/share/lynx-tools/calls
cp -p /usr/local/bin/lynx-noobd /usr/local/bin/lynx-noobd.before-hardware-status-gnss-fix
cp -p /usr/local/bin/lynx_hardware.py /usr/local/bin/lynx_hardware.py.before-gnss-fix
"""
        for local, target in FILES.items():
            stage_script += f"cp {STAGE}/{local.name} {target}.hw.new\n"
            mode = 0o755 if (local.suffix == ".sh" or target.endswith("lynx-noobd") or
                              target.endswith("lynx_hardware.py") or
                              target.endswith("lynx_microphone_level.py")) else 0o644
            stage_script += f"chmod {mode:o} {target}.hw.new\n"
            stage_script += f"mv {target}.hw.new {target}\n"
        stage_script += "ln -sf lynx_hardware.py /usr/local/bin/lynx-hardware\n"
        stage_script += "ln -sf lynx_microphone_level.py /usr/local/bin/lynx-mic-level\n"
        stage_script += "rc-service lynx-noobd restart\nrc-service lynx-noobd status\n"
        installed = True
        step("install", stage_script, timeout=60)
        result = json.loads(step("local_inventory", "/usr/local/bin/lynx-hardware status all"))
        report["local_inventory"] = result
        time.sleep(1)
        for name in ("MIC", "FLASH", "GNSS", "BT", "CAMERA"):
            check = subprocess.run(["python3", str(ROOT / "tools/lynx_noobctl.py"),
                                    "CALL", name + "_STATUS"], capture_output=True,
                                   text=True, timeout=8)
            response = check.stdout.strip()
            report["steps"].append({"name": "nrp_" + name.lower(), "exit": check.returncode,
                                    "stdout": response, "stderr": check.stderr[-300:]})
            if check.returncode:
                raise RuntimeError(f"{name} NRP status call failed")
            if " OK value=0 detail=interface_ready=" not in response:
                raise RuntimeError(f"{name} status response unexpected")
        after = json.loads(step("health_after", "/usr/local/bin/lynx-status --assert-ready"))
        if after["boot_id"] != report["boot_id"] or after["issues"]:
            raise RuntimeError("health changed after install")
        report["state"] = "installed-and-verified"
    except Exception as exc:
        report.update(state="failed", error=str(exc))
        if installed:
            result = remote("cp -p /usr/local/bin/lynx-noobd.before-hardware-status-gnss-fix "
                            "/usr/local/bin/lynx-noobd; "
                            "cp -p /usr/local/bin/lynx_hardware.py.before-gnss-fix "
                            "/usr/local/bin/lynx_hardware.py; rc-service lynx-noobd restart", timeout=35)
            report["rollback_exit"] = result.returncode
    (receipt / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "receipt": str(receipt / "result.json"),
                      "error": report.get("error")}))
    if report["state"] != "installed-and-verified":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
