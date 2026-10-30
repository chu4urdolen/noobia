#!/usr/bin/env python3
"""Eight-second RAM-only mnld trial with only /dev/gpsdl0 and a reboot guard."""

import hashlib
import json
from pathlib import Path
import argparse
import subprocess
import time

from lynx_wifi_v19_contact import ssh_command
from parse_lynx_mnl_nmea import summarize

ROOT = Path(__file__).resolve().parent.parent
V52_SHA = "9206aafb339ad66b2d942ea5795b8f476a5eaf3a148f9cdfc76be22cb83e30bf"
BUNDLE = "/run/lynx-gnss-static"


def phone(command, data=None, timeout=18):
    argv = ssh_command("192.168.100.107", command)
    argv[-2:-2] = ["-p", "2222"]
    return subprocess.run(argv, input=data, capture_output=True, timeout=timeout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--power-nodes", action="store_true",
                        help="expose verified gps_emi and gps_pwr as well")
    parser.add_argument("--scp-node", action="store_true",
                        help="also expose verified gps2scp")
    parser.add_argument("--capture-mnl", action="store_true",
                        help="capture, but do not reply to, mnld's HAL messages")
    parser.add_argument("--start-mnl", action="store_true",
                        help="issue stock start and stop packets during the bounded trial")
    parser.add_argument("--capture-logd", action="store_true",
                        help="capture Android log messages in the RAM sandbox")
    parser.add_argument("--port2", action="store_true",
                        help="expose the verified second GPS data link")
    parser.add_argument("--sky-trial", action="store_true",
                        help="60-second guarded receiver trial after sky view is confirmed")
    args = parser.parse_args()
    if args.sky_trial:
        args.start_mnl = True
        args.capture_logd = True
        args.port2 = True
    if args.port2:
        args.scp_node = True
    if args.start_mnl:
        args.capture_mnl = True
    if args.capture_mnl:
        args.scp_node = True
    if args.scp_node:
        args.power_nodes = True
    out = ROOT / "logs" / f"v52-gnss-mnld-{time.time_ns()}"
    out.mkdir(mode=0o700)
    remote = "/run/lynx-gnss-mnld-trial-" + str(time.time_ns())
    report = {"state": "preflight", "partition_writes": False,
              "device_nodes_exposed": (["/dev/gpsdl0", "/dev/gpsdl1", "/dev/gps_emi", "/dev/gps_pwr", "/dev/gps2scp"]
                                       if args.port2 else
                                       ["/dev/gpsdl0", "/dev/gps_emi", "/dev/gps_pwr", "/dev/gps2scp"]
                                       if args.scp_node else
                                       ["/dev/gpsdl0", "/dev/gps_emi", "/dev/gps_pwr"]
                                       if args.power_nodes else ["/dev/gpsdl0"]), "position_fix": False,
              "remote": remote, "steps": []}
    armed = False

    def save():
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")

    def step(name, command, data=None, timeout=18):
        result = phone(command, data, timeout)
        (out / f"{name}.stdout").write_bytes(result.stdout)
        (out / f"{name}.stderr").write_bytes(result.stderr)
        report["steps"].append({"name": name, "exit": result.returncode})
        save()
        if result.returncode:
            raise RuntimeError(name + " failed")
        return result.stdout.decode(errors="replace").strip()

    save()
    try:
        identity = step("identity", "cat /proc/sys/kernel/random/boot_id; "
                        "sha256sum /dev/sdc39 | cut -c1-64").splitlines()
        if len(identity) != 2 or identity[1] != V52_SHA:
            raise RuntimeError("not exact V52 boot")
        report["boot_id"] = identity[0]
        health = json.loads(step("health_before", "/usr/local/bin/lynx-status --assert-ready"))
        if (health["boot_id"] != identity[0] or health["issues"] or
                health["battery"]["capacity_percent"] < 50 or
                health["battery"]["temperature_mC"] >= 35000 or
                health["thermal"]["max_mC"] >= 45000):
            raise RuntimeError("power or service guard failed")
        step("device_preflight", "set -eu; test -d /sys/module/gps_drv_dl_v050; "
             "test -c /dev/gpsdl0; ! pgrep -x mnld; "
             + ("test -d /sys/module/gps_pwr; test -c /dev/gps_pwr; test -c /dev/gps_emi; "
                if args.power_nodes else "")
             + ("test -d /sys/module/gps_scp; test -c /dev/gps2scp; "
                if args.scp_node else "")
             + ("test -c /dev/gpsdl1; " if args.port2 else "")
             + f"test -f {BUNDLE}/bin/mnld; test -f {BUNDLE}/lib64/liblynx_props.so")
        runner = (ROOT / "tools/lynx_gnss_sandbox_runner.py").read_bytes()
        digest = hashlib.sha256(runner).hexdigest()
        step("runner_stage", f"cat > /run/lynx_gnss_sandbox_runner.py; "
             f'test "$(sha256sum /run/lynx_gnss_sandbox_runner.py | cut -c1-64)" = {digest}', runner)
        if args.capture_mnl:
            listener = (ROOT / "tools/lynx_mnl_listener.py").read_bytes()
            listener_digest = hashlib.sha256(listener).hexdigest()
            step("listener_stage", "cat > /run/lynx_mnl_listener.py; "
                 f'test "$(sha256sum /run/lynx_mnl_listener.py | cut -c1-64)" = {listener_digest}', listener)
        shim = (ROOT / "linux-port/artifacts/stock-cph2493-August-eu-ota/gnss-reference"
                "/mnld-static-deps-bundle/lib64/liblynx_props.so").read_bytes()
        shim_digest = hashlib.sha256(shim).hexdigest()
        step("props_stage", f"cat > {BUNDLE}/lib64/liblynx_props.so; "
             f'test "$(sha256sum {BUNDLE}/lib64/liblynx_props.so | cut -c1-64)" = {shim_digest}', shim)
        custom = (ROOT / "linux-port/artifacts/stock-cph2493-August-eu-ota/gnss-reference"
                  "/mnld-static-deps-bundle/lib64/libcustom_nvram.so").read_bytes()
        custom_digest = hashlib.sha256(custom).hexdigest()
        step("custom_nvram_stage", f"cat > {BUNDLE}/lib64/libcustom_nvram.so; "
             f'test "$(sha256sum {BUNDLE}/lib64/libcustom_nvram.so | cut -c1-64)" = {custom_digest}', custom)
        step("remote_dir", f"mkdir -m 700 {remote}")
        watchdog_seconds = 115 if args.sky_trial else 75
        watchdog = (f"#!/bin/sh\nsleep {watchdog_seconds}\n"
                    f"test -e {remote}/cancel && exit 0\n"
                    f"echo reboot > {remote}/watchdog-state\nexec /sbin/reboot\n")
        step("watchdog_stage", f"cat > {remote}/watchdog.sh; chmod 700 {remote}/watchdog.sh",
             watchdog.encode())
        armed = True
        step("watchdog_arm", f"/usr/bin/setsid /bin/sh {remote}/watchdog.sh "
             f"</dev/null >{remote}/watchdog.log 2>&1 & "
             f"echo $! > {remote}/pid; sleep 0.1; kill -0 $(cat {remote}/pid)")
        raw = step("mnld_sandbox", f"/usr/bin/timeout -k 2 {80 if args.sky_trial else 35 if args.start_mnl else 18} "
                   f"/usr/bin/python3 /run/lynx_gnss_sandbox_runner.py {BUNDLE} --gpsdl0 --factory-gps --strace"
                   f"{' --gps-power-nodes' if args.power_nodes else ''}"
                   f"{' --gps-scp-node' if args.scp_node else ''}"
                   f"{' --gps-port2' if args.port2 else ''}"
                   f"{' --capture-mnl' if args.capture_mnl else ''}"
                   f"{' --start-mnl' if args.start_mnl else ''}"
                   f"{' --capture-logd' if args.capture_logd else ''}"
                   f"{' --sky-trial' if args.sky_trial else ''}",
                   timeout=90 if args.sky_trial else 42 if args.start_mnl else 24)
        report["sandbox"] = json.loads(raw)
        if args.start_mnl:
            summary = summarize(report)
            (out / "nmea-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
            report["nmea_summary"] = summary
            report["position_fix"] = summary["position_fix"]
        report["state"] = "sandbox-complete"
        step("kernel_log", "dmesg | tail -n 120")
        after = json.loads(step("health_after", "/usr/local/bin/lynx-status --assert-ready"))
        if after["boot_id"] != identity[0] or after["issues"] or not after["wifi"]["carrier"]:
            raise RuntimeError("Alpine health changed")
        step("no_daemon_left", "! pgrep -x mnld; ! ls -d /run/lynx-gnss-sandbox-* 2>/dev/null")
        report["state"] = "sandbox-complete-healthy"
    except Exception as exc:
        report.update(state="failed-or-contact-lost", error=str(exc))
    finally:
        if armed and report["state"] == "sandbox-complete-healthy":
            try:
                report["watchdog_cancelled"] = phone(f"touch {remote}/cancel; test -e {remote}/cancel",
                                                     timeout=8).returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                report["watchdog_cancelled"] = False
        if armed and not report.get("watchdog_cancelled"):
            report["watchdog_reboot_expected_within_seconds"] = 115 if args.sky_trial else 75
        save()
    print(json.dumps({"state": report["state"], "receipt": str(out / "result.json"),
                      "watchdog_cancelled": report.get("watchdog_cancelled"),
                      "error": report.get("error")}))
    if report["state"] != "sandbox-complete-healthy" or not report.get("watchdog_cancelled"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
