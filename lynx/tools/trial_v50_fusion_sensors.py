#!/usr/bin/env python3
"""Sample Lynx's registered fusion sensors from a temporary helper."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "tools/lynx_hf_sample.py"
REMOTE = "/run/lynx-hf-fusion-trial.py"
SENSORS = {9: "gravity", 10: "linear_acc", 11: "rot_vec", 3: "orientation"}


def ssh(command, data=None, timeout=15):
    args = ssh_command("192.168.100.107", command)
    args[-2:-2] = ["-p", "2222"]
    return subprocess.run(args, input=data, capture_output=True, timeout=timeout)


def main():
    receipt = ROOT / "logs" / f"v50-hf-fusion-{time.time_ns()}"
    receipt.mkdir(mode=0o700)
    report = {"state": "preflight", "persistent_changes": False, "steps": []}

    def step(name, command, data=None, timeout=15):
        proc = ssh(command, data, timeout)
        (receipt / f"{name}.stdout").write_bytes(proc.stdout)
        (receipt / f"{name}.stderr").write_bytes(proc.stderr)
        report["steps"].append({"name": name, "exit": proc.returncode})
        if proc.returncode:
            raise RuntimeError(f"{name} failed")
        return proc.stdout.decode(errors="replace").strip()

    try:
        health = json.loads(step("health", "/usr/local/bin/lynx-status --assert-ready"))
        if health["battery"]["capacity_percent"] < 25 or \
           health["battery"]["temperature_mC"] >= 35000 or \
           health["thermal"]["max_mC"] >= 45000:
            raise RuntimeError("health guard failed")
        report["boot_id"] = health["boot_id"]
        step("preflight", "set -eu; rc-service lynx-sensorhub status; "
             "test -c /dev/hf_manager; test ! -e /run/lynx-hf-fusion-trial.py")
        data = SOURCE.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        step("stage", f"cat > {REMOTE}; chmod 700 {REMOTE}; "
             f'test "$(sha256sum {REMOTE} | cut -c1-64)" = {digest}', data)
        report["samples"] = {}
        for sensor, name in SENSORS.items():
            sample = json.loads(step(name, f"/usr/bin/python3 {REMOTE} --sensor {sensor} "
                                     "--seconds 1 --events 4", timeout=8))
            if not sample.get("disabled") or sample.get("sensor_type") != sensor:
                raise RuntimeError(f"{name} did not disable cleanly")
            report["samples"][name] = {"events": len(sample["events"]), "info": sample["info"]}
        active = step("idle", "sed -n '/^Active List:/,/^Debug Sub Module:/p' "
                      "/proc/hf_manager | head -4")
        if "Active List:\n**************************************************\nDebug Sub Module:" not in active:
            raise RuntimeError("sensor manager still has active clients")
        step("post_health", "/usr/local/bin/lynx-status --assert-ready >/dev/null")
        report["state"] = "sampled-idle-healthy"
    except Exception as exc:
        report.update(state="failed", error=str(exc))
    finally:
        cleanup = ssh(f"rm -f {REMOTE}")
        (receipt / "cleanup.stdout").write_bytes(cleanup.stdout)
        (receipt / "cleanup.stderr").write_bytes(cleanup.stderr)
        report["cleanup_exit"] = cleanup.returncode
    (receipt / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"state": report["state"], "receipt": str(receipt / "result.json"),
                      "samples": report.get("samples"), "error": report.get("error")}))
    if report["state"] != "sampled-idle-healthy":
        sys.exit(1)


if __name__ == "__main__":
    main()
