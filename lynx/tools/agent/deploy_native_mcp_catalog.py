#!/usr/bin/env python3
"""Atomically stage Lynx's native MCP manifests and both catalog readers."""

import argparse
import hashlib
import io
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
import time

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
from lynx_wifi_v19_contact import ssh_command  # noqa: E402

HOST = "192.168.100.107"
OLD_AGENT_SHA = "68659e7336e0d848b3405703de140e0262c63ee192f72ecf6f61c27228e600a3"
OLD_RUNTIME_SHA = "125c2e6dae02a6831bfb8decaba7470586c569318d3bc227e45899dd36a623e8"
CATALOG = "/usr/local/share/lynx/agent-tools"
MANIFESTS = (
    "lynx_agent_health", "lynx_bluetooth", "lynx_camera", "lynx_codex",
    "lynx_flashlight", "lynx_flashlight_pulse", "lynx_flashlight_stop",
    "lynx_gnss", "lynx_light_read", "lynx_magnetometer_read",
    "lynx_microphone", "lynx_microphone_level", "lynx_motion_read",
    "lynx_proximity_read", "lynx_queue_health",
)
FILES = (
    (TOOLS / "agent/lynx_agent.py", "/usr/local/bin/lynx-agent", "lynx-agent", 0o755),
    (TOOLS / "lynx_noob_runtime.py", "/usr/local/bin/lynx-noobd", "lynx-noobd", 0o755),
    *((TOOLS / "local_calls" / (name + ".json"), CATALOG + "/" + name + ".json",
       "manifests/" + name + ".json", 0o644) for name in MANIFESTS),
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def phone(command, data=None, timeout=25):
    argv = ssh_command(HOST, command)
    argv[-2:-2] = ["-p", "2222"]
    try:
        result = subprocess.run(argv, input=data, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Lynx SSH timeout") from exc
    if result.returncode:
        raise RuntimeError("Lynx SSH command failed: " +
                           result.stderr.decode(errors="replace")[-300:])
    return result.stdout


def local_files():
    files = {}
    for source, target, archive, mode in FILES:
        data = source.read_bytes()
        if archive.endswith(".json"):
            meta = json.loads(data)
            if (meta.get("name") != source.stem or
                    not isinstance(meta.get("inputSchema"), dict)):
                raise RuntimeError("invalid local MCP manifest: " + source.name)
        files[archive] = (data, target, mode)
    for archive in ("lynx-agent", "lynx-noobd"):
        compile(files[archive][0], archive, "exec")
    return files


def preflight(files):
    health = json.loads(phone("/usr/local/bin/lynx-status --assert-ready"))
    if (health.get("issues") or not health.get("wifi", {}).get("carrier") or
            health["battery"]["capacity_percent"] < 50 or
            health["battery"]["temperature_mC"] >= 35000 or
            health["thermal"]["max_mC"] >= 45000):
        raise RuntimeError("Lynx power, thermal, or service guard failed")
    queue = json.loads(phone("/usr/local/bin/lynx-agent-health"))
    if queue.get("issues") or queue.get("counts", {}).get("running"):
        raise RuntimeError("Lynx agent queue is busy or unhealthy")
    old = {}
    for archive, (data, target, _mode) in files.items():
        prior = phone("cat " + shlex.quote(target))
        old[archive] = sha(prior)
        if archive == "lynx-agent" and old[archive] != OLD_AGENT_SHA:
            raise RuntimeError("Lynx agent differs from reviewed baseline")
        if archive == "lynx-noobd" and old[archive] != OLD_RUNTIME_SHA:
            raise RuntimeError("Lynx runtime differs from reviewed baseline")
        if archive.endswith(".json"):
            before, after = json.loads(prior), json.loads(data)
            for key in ("description", "timeout", "nrp_id", "nrp_result"):
                if before.get(key) != after.get(key):
                    raise RuntimeError("manifest behavior changed: " + archive)
            if before.get("parameters") != after.get("inputSchema"):
                raise RuntimeError("manifest argument schema changed: " + archive)
    return health, queue, old


def archive_payload(files):
    output = io.BytesIO()
    checksums = []
    with tarfile.open(fileobj=output, mode="w") as tar:
        directory = tarfile.TarInfo("manifests/")
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o700
        tar.addfile(directory)
        for name, (data, _target, mode) in files.items():
            info = tarfile.TarInfo(name)
            info.mode = mode
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
            checksums.append(f"{sha(data)}  {name}")
        data = ("\n".join(checksums) + "\n").encode()
        info = tarfile.TarInfo("SHA256SUMS")
        info.mode = 0o600
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    return output.getvalue()


def restore_command(files, backup):
    commands = ["set -eu"]
    for name, (_data, target, _mode) in files.items():
        source = shlex.quote(backup + "/" + name)
        candidate = shlex.quote(target + ".mcp-rollback")
        commands.append(f"cp -p {source} {candidate}; mv -f {candidate} {shlex.quote(target)}")
    commands.append("rc-service lynx-noobd restart")
    return "; ".join(commands)


def deploy(files, report):
    stamp = str(time.time_ns())
    stage = "/run/lynx-native-mcp-" + stamp
    backup = "/usr/local/share/lynx/backups/native-mcp-" + stamp
    report.update(stage=stage, backup=backup, watchdog_seconds=180)
    payload = archive_payload(files)
    phone(f"mkdir -m 700 {stage}; tar -xf - -C {stage}; "
          f"cd {stage}; sha256sum -c SHA256SUMS >/dev/null; "
          "python3 -m py_compile lynx-agent lynx-noobd", payload, timeout=35)
    report["state"] = "staged"
    report["save"]()
    commands = ["set -eu", f"mkdir -p -m 700 {backup}",
                f"mkdir -m 700 {backup}/manifests"]
    for name, (_data, target, _mode) in files.items():
        commands.append(f"cp -p {shlex.quote(target)} {shlex.quote(backup + '/' + name)}")
    phone("; ".join(commands), timeout=35)
    report["backup_ready"] = True
    report["state"] = "backed-up"
    report["save"]()
    rollback = restore_command(files, backup)
    watchdog = ("#!/bin/sh\nsleep 180\n" +
                f"test -e {stage}/cancel && exit 0\n" +
                rollback + "\n")
    phone(f"cat > {stage}/rollback.sh; chmod 700 {stage}/rollback.sh", watchdog.encode())
    phone(f"/usr/bin/setsid /bin/sh {stage}/rollback.sh </dev/null "
          f">{stage}/rollback.log 2>&1 & echo $! > {stage}/rollback.pid; "
          f"sleep 0.1; kill -0 $(cat {stage}/rollback.pid)")
    report["state"] = "watchdog-armed"
    report["save"]()
    commands = ["set -eu"]
    for name, (data, target, mode) in files.items():
        candidate = target + ".mcp-candidate"
        commands.append(f"install -m {mode:o} {shlex.quote(stage + '/' + name)} "
                        f"{shlex.quote(candidate)}; mv -f {shlex.quote(candidate)} "
                        f"{shlex.quote(target)}")
    phone("; ".join(commands), timeout=35)
    report["state"] = "installed"
    report["save"]()
    for name, (data, target, _mode) in files.items():
        actual = phone("sha256sum " + shlex.quote(target)).decode().split()[0]
        if actual != sha(data):
            raise RuntimeError("installed checksum mismatch: " + name)
    phone("rc-service lynx-noobd restart", timeout=35)
    time.sleep(1)
    state = json.loads(phone("/usr/local/bin/lynx-status --assert-ready"))
    if state["boot_id"] != report["boot_id"] or state.get("issues"):
        raise RuntimeError("Lynx health changed after MCP deployment")
    caps_code = ("import socket; s=socket.socket(socket.AF_UNIX); "
                 "s.settimeout(3); s.connect('/run/lynx/noobd.sock'); "
                 "s.sendall(b'NRP/1 7 CAPS\\n'); print(s.recv(8192).decode())")
    caps = phone("python3 -c " + shlex.quote(caps_code)).decode(errors="replace")
    if "500:LYNX_AGENT_HEALTH" not in caps or "514:LYNX_QUEUE_HEALTH" not in caps:
        raise RuntimeError("NRP catalog registration missing after MCP deployment")
    count = int(phone("python3 -c \"import runpy; d=runpy.run_path('/usr/local/bin/lynx-agent'); "
                      "print(len(d['Catalog']().definitions()))\"").decode().strip())
    if count != len(MANIFESTS):
        raise RuntimeError("agent catalog count mismatch")
    sample = json.loads(phone("python3 -c \"import runpy,json; d=runpy.run_path('/usr/local/bin/lynx-agent'); "
                              "print(json.dumps(d['Catalog']().run('lynx_light_read', {})))\""))
    if not sample.get("ok"):
        raise RuntimeError("converted MCP tool invocation failed")
    queue = json.loads(phone("/usr/local/bin/lynx-agent-health"))
    if queue.get("issues") or queue.get("counts", {}).get("running"):
        raise RuntimeError("agent queue health changed")
    phone(f"touch {stage}/cancel; test -e {stage}/cancel")
    report.update(state="installed-healthy", watchdog_cancelled=True,
                  catalog_count=count, light_tool_ok=True, nrp_catalog_ok=True,
                  health_after={"boot_id": state["boot_id"], "issues": state["issues"],
                                "battery_percent": state["battery"]["capacity_percent"]})
    report["save"]()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--deploy", action="store_true")
    args = parser.parse_args()
    files = local_files()
    health, queue, old = preflight(files)
    if args.dry_run:
        print(json.dumps({"state": "ready-no-write", "boot_id": health["boot_id"],
                          "battery_percent": health["battery"]["capacity_percent"],
                          "file_count": len(files), "running_jobs": queue["counts"]["running"]}))
        return
    out = ROOT / "logs" / f"native-mcp-deploy-{time.time_ns()}"
    out.mkdir(mode=0o700)
    report = {"schema": 1, "state": "preflight", "boot_id": health["boot_id"],
              "old_sha256": old, "new_sha256": {name: sha(data) for name, (data, _, _) in files.items()},
              "partition_writes": False, "started_ns": time.time_ns()}

    def save():
        (out / "result.json").write_text(json.dumps({k: v for k, v in report.items()
                                                       if k != "save"}, indent=2) + "\n")

    report["save"] = save
    save()
    try:
        deploy(files, report)
    except Exception as exc:
        report.update(state="failed", error=str(exc))
        if report.get("backup_ready"):
            try:
                phone(restore_command(files, report["backup"]), timeout=35)
                if report.get("stage"):
                    phone(f"touch {report['stage']}/cancel; test -e {report['stage']}/cancel")
                report["rollback_ok"] = True
            except Exception as rollback_exc:
                report["rollback_ok"] = False
                report["rollback_error"] = str(rollback_exc)
        save()
        print(json.dumps({"state": report["state"], "receipt": str(out / "result.json"),
                          "rollback_ok": report.get("rollback_ok"), "error": report["error"]}))
        raise SystemExit(1)
    print(json.dumps({"state": report["state"], "receipt": str(out / "result.json"),
                      "catalog_count": report["catalog_count"],
                      "watchdog_cancelled": report["watchdog_cancelled"]}))


if __name__ == "__main__":
    main()
