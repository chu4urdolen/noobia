#!/usr/bin/env python3
"""Guarded V52 Bluetooth H4 command trial. No pairing, disk writes, or flashing."""

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile
import threading
import time

from lynx_wifi_v19_contact import ssh_command

ROOT = Path(__file__).resolve().parent.parent
V52_SHA = "9206aafb339ad66b2d942ea5795b8f476a5eaf3a148f9cdfc76be22cb83e30bf"
KERNEL = "5.10.149-android12-9-o-g311738fbb5a8"
FIRMWARE = ROOT / "linux-port/artifacts/stock-cph2493-August-eu-ota/wifi-reference/vendor-unpacked/firmware"
FILES = ("BT_FW.cfg", "soc7_0_ram_bt_1_1_hdr.bin", "soc7_0_ram_bt_1a_1_hdr.bin",
         "soc7_0_ram_bt_1b_1_hdr.bin", "soc7_0_ram_mcu_1_1_hdr.bin",
         "soc7_0_ram_mcu_1a_1_hdr.bin", "soc7_0_ram_mcu_1b_1_hdr.bin")


def phone(command, data=None, timeout=18):
    argv = ssh_command("192.168.100.107", command)
    argv[-2:-2] = ["-p", "2222"]
    return subprocess.run(argv, input=data, capture_output=True, timeout=timeout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discover", action="store_true",
                        help="advertise Lynx for 18 seconds while Nexus performs a bounded LE scan")
    parser.add_argument("--connect", action="store_true",
                        help="attempt one bounded Nexus LE connection; no pairing")
    parser.add_argument("--factory-address-receipt", type=Path,
                        help="read-only nvdata receipt for temporary controller address trial")
    parser.add_argument("--hciuart-bridge", action="store_true",
                        help="bounded RAM-only bridge from stpbt to built-in HCI UART")
    parser.add_argument("--bluez-query", action="store_true",
                        help="query temporary HCI controller through BlueZ; implies bridge")
    parser.add_argument("--bluez-power", action="store_true",
                        help="power on the temporary BlueZ controller without pairing")
    parser.add_argument("--gatt-probe", action="store_true",
                        help="temporarily register read-only PING/INFO GATT endpoint")
    args = parser.parse_args()
    if args.gatt_probe:
        args.bluez_power = True
        if not args.factory_address_receipt:
            parser.error("GATT probe requires a verified factory address receipt")
    if args.bluez_power:
        args.bluez_query = True
    if args.bluez_query:
        args.hciuart_bridge = True
    if args.hciuart_bridge and (args.discover or args.connect):
        parser.error("HCI UART bridge trial cannot be combined with advertising")
    if args.connect:
        args.discover = True
    factory_address = None
    if args.factory_address_receipt:
        receipt = args.factory_address_receipt.resolve(strict=True)
        if not receipt.is_relative_to(ROOT / "logs"):
            parser.error("factory receipt must be under Lynx logs")
        evidence = json.loads(receipt.read_text())
        factory_address = evidence.get("address")
        if (evidence.get("partition") != "nvdata" or
                evidence.get("mount_options") != "ro,noload,nosuid,nodev,noexec" or
                evidence.get("partition_writes") is not False or
                not isinstance(factory_address, str) or
                not re.fullmatch(r"[0-9A-F]{2}(?::[0-9A-F]{2}){5}", factory_address) or
                factory_address.startswith("00:00:46")):
            parser.error("invalid read-only factory address receipt")
    out = ROOT / "logs" / f"v52-bluetooth-hci-{time.time_ns()}"
    out.mkdir(mode=0o700)
    remote = "/run/lynx-bt-hci-" + str(time.time_ns())
    report = {"state": "preflight", "boot_partition_writes": False,
              "paired": False, "remote": remote, "steps": [],
              "started_at_utc": datetime.now(timezone.utc).isoformat(),
              "started_monotonic_ns": time.monotonic_ns()}
    armed = False
    firmware_path = None
    scanner = None
    scan_file = None
    connector = None
    connect_results = {}
    bluez_thread = None
    bluez_results = {}
    gatt_thread = None
    gatt_results = {}
    nexus_thread = None
    nexus_results = {}

    def query_bluez():
        power_command = ("n=0; until /usr/bin/bluetoothctl power on; "
                         "do n=$((n+1)); test $n -lt 8; sleep 0.5; done; sleep 1; "
                         if args.bluez_power else "")
        command = ("set -eu; n=0; until test -d /sys/class/bluetooth/hci0; "
                   "do n=$((n+1)); test $n -lt 40; sleep 0.2; done; sleep 1; "
                   f"/usr/bin/python3 {remote}/mgmt.py; "
                   "rc-service dbus start; rc-service bluetooth start; "
                   + power_command + "/usr/bin/bluetoothctl show")
        try:
            result = phone(command, timeout=22)
            (out / "bluez-query.stdout").write_bytes(result.stdout)
            (out / "bluez-query.stderr").write_bytes(result.stderr)
            bluez_results.update(exit=result.returncode,
                                 controller_seen=b"Controller " in result.stdout,
                                 powered=b"Powered: yes" in result.stdout,
                                 factory_identity_seen=(not factory_address or
                                     b"Controller " + factory_address.encode() in result.stdout))
        except (OSError, subprocess.TimeoutExpired) as exc:
            bluez_results.update(error=str(exc))

    def query_gatt():
        bluez_thread.join(timeout=15)
        if bluez_results.get("exit") != 0 or not bluez_results.get("powered"):
            gatt_results["error"] = "BlueZ not powered"
            return
        try:
            result = phone(f"PYTHONPATH={remote}/vendor /usr/bin/python3 "
                           f"{remote}/gatt.py --seconds 28", timeout=37)
            (out / "gatt.stdout").write_bytes(result.stdout)
            (out / "gatt.stderr").write_bytes(result.stderr)
            gatt_results.update(exit=result.returncode,
                                registered=b"GATT_READY" in result.stdout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            gatt_results.update(error=str(exc))

    def query_nexus_ping():
        try:
            command = ["python3", str(ROOT / "tools/lynx_ble_nexus_ping.py"),
                       "--factory-address-receipt", str(args.factory_address_receipt),
                       "--seconds", "32"]
            result = subprocess.run(command, capture_output=True, timeout=40,
                                    env={"PYTHONPATH": str(ROOT / "tools/vendor_dbus_next") +
                                         ":" + str(ROOT / "tools")})
            (out / "nexus-gatt.stdout").write_bytes(result.stdout)
            (out / "nexus-gatt.stderr").write_bytes(result.stderr)
            nexus_results.update(exit=result.returncode)
            if result.returncode == 0:
                nexus_results.update(json.loads(result.stdout))
        except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
            nexus_results.update(error=str(exc))

    def connect_from_nexus():
        scan = subprocess.run(["bluetoothctl", "--timeout", "8", "scan", "le"],
                              capture_output=True, text=True, timeout=13)
        (out / "nexus-le-scan.txt").write_text(scan.stdout + scan.stderr)
        subprocess.run(["bluetoothctl", "scan", "off"], capture_output=True, timeout=6)
        address = factory_address or "00:00:46:67:61:01"
        if address not in (scan.stdout + scan.stderr).upper() or "Lynx" not in scan.stdout:
            connect_results["state"] = "lynx-not-in-scan"
            return
        result = subprocess.run(["bluetoothctl", "--timeout", "12", "connect", address],
                                capture_output=True, text=True, timeout=17)
        (out / "nexus-le-connect.txt").write_text(result.stdout + result.stderr)
        connect_results.update(state="attempted", exit=result.returncode,
                               output=(result.stdout + result.stderr)[-1500:])
        disconnect = subprocess.run(["bluetoothctl", "disconnect", address],
                                    capture_output=True, text=True, timeout=8)
        (out / "nexus-le-disconnect.txt").write_text(disconnect.stdout + disconnect.stderr)

    def save():
        tmp = out / "result.tmp"
        tmp.write_text(json.dumps(report, indent=2) + "\n")
        tmp.replace(out / "result.json")

    def step(name, command, data=None, timeout=18):
        started_wall = datetime.now(timezone.utc).isoformat()
        started_monotonic = time.monotonic_ns()
        try:
            result = phone(command, data, timeout)
        except subprocess.TimeoutExpired as exc:
            (out / f"{name}.stdout").write_bytes(exc.stdout or b"")
            (out / f"{name}.stderr").write_bytes(exc.stderr or b"")
            report["steps"].append({"name": name, "timeout": True,
                                    "started_at_utc": started_wall,
                                    "started_monotonic_ns": started_monotonic,
                                    "ended_monotonic_ns": time.monotonic_ns()})
            save()
            raise RuntimeError(name + " timed out") from None
        (out / f"{name}.stdout").write_bytes(result.stdout)
        (out / f"{name}.stderr").write_bytes(result.stderr)
        report["steps"].append({"name": name, "exit": result.returncode,
                                "started_at_utc": started_wall,
                                "started_monotonic_ns": started_monotonic,
                                "ended_monotonic_ns": time.monotonic_ns()})
        save()
        if result.returncode:
            raise RuntimeError(name + " failed")
        return result.stdout.decode(errors="replace").strip()

    save()
    try:
        identity = step("identity", "cat /proc/sys/kernel/random/boot_id; "
                        "uname -r; sha256sum /dev/sdc39 | cut -c1-64").splitlines()
        if len(identity) != 3 or identity[1:] != [KERNEL, V52_SHA]:
            raise RuntimeError("phone is not booted from exact V52 image")
        report["boot_id"] = identity[0]
        health = json.loads(step("health_before", "/usr/local/bin/lynx-status --assert-ready"))
        if (health["boot_id"] != identity[0] or health["issues"] or
                health["battery"]["capacity_percent"] < 50 or
                health["battery"]["temperature_mC"] >= 35000 or
                health["thermal"]["max_mC"] >= 45000):
            raise RuntimeError("power or service health guard failed")
        step("device_preflight", "set -eu; test -d /sys/module/bt_drv_6983; "
             "test -c /dev/stpbt; rc-service lynx-wifi status")
        if args.bluez_query:
            step("bluez_preflight", "set -eu; apk info -e bluez; "
                 "! rc-service dbus status >/dev/null 2>&1; "
                 "! rc-service bluetooth status >/dev/null 2>&1")
        firmware_path = step("firmware_path_before", "cat /sys/module/firmware_class/parameters/path")
        step("remote_dir", f"mkdir -m 700 {remote}; mkdir -m 700 {remote}/firmware")
        for name in FILES:
            data = (FIRMWARE / name).read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            step("firmware_" + name, f"cat > {remote}/firmware/{name}; "
                 f'test "$(sha256sum {remote}/firmware/{name} | cut -c1-64)" = {digest}', data)
        probe = (ROOT / "tools/lynx_stpbt_hciuart_bridge.py" if args.hciuart_bridge else
                 ROOT / "tools/lynx_bluetooth_hci_probe.py").read_bytes()
        digest = hashlib.sha256(probe).hexdigest()
        step("probe_stage", f"cat > {remote}/probe.py; "
             f'test "$(sha256sum {remote}/probe.py | cut -c1-64)" = {digest}; '
             f"/usr/bin/python3 -m py_compile {remote}/probe.py", probe)
        if args.hciuart_bridge and factory_address:
            hci_source = (ROOT / "tools/lynx_bluetooth_hci_probe.py").read_bytes()
            hci_sha = hashlib.sha256(hci_source).hexdigest()
            step("hci_helper_stage", f"cat > {remote}/lynx_bluetooth_hci_probe.py; "
                 f'test "$(sha256sum {remote}/lynx_bluetooth_hci_probe.py | cut -c1-64)" = {hci_sha}; '
                 f"/usr/bin/python3 -m py_compile {remote}/lynx_bluetooth_hci_probe.py",
                 hci_source)
        if args.bluez_query:
            mgmt = (ROOT / "tools/lynx_bt_mgmt_query.py").read_bytes()
            mgmt_sha = hashlib.sha256(mgmt).hexdigest()
            step("mgmt_stage", f"cat > {remote}/mgmt.py; "
                 f'test "$(sha256sum {remote}/mgmt.py | cut -c1-64)" = {mgmt_sha}; '
                 f"/usr/bin/python3 -m py_compile {remote}/mgmt.py", mgmt)
        if args.gatt_probe:
            gatt_source = (ROOT / "tools/lynx_ble_gatt_probe.py").read_bytes()
            gatt_sha = hashlib.sha256(gatt_source).hexdigest()
            step("gatt_stage", f"cat > {remote}/gatt.py; "
                 f'test "$(sha256sum {remote}/gatt.py | cut -c1-64)" = {gatt_sha}; '
                 f"/usr/bin/python3 -m py_compile {remote}/gatt.py", gatt_source)
            archive = io.BytesIO()
            with tarfile.open(fileobj=archive, mode="w:gz") as tar:
                tar.add(ROOT / "tools/vendor_dbus_next/dbus_next", arcname="dbus_next",
                        filter=lambda item: None if "__pycache__" in item.name else item)
            payload = archive.getvalue()
            vendor_sha = hashlib.sha256(payload).hexdigest()
            step("gatt_vendor_stage", f"cat > {remote}/vendor.tar.gz; "
                 f'test "$(sha256sum {remote}/vendor.tar.gz | cut -c1-64)" = {vendor_sha}; '
                 f"mkdir {remote}/vendor; tar -xzf {remote}/vendor.tar.gz -C {remote}/vendor; "
                 f"PYTHONPATH={remote}/vendor /usr/bin/python3 -c 'import dbus_next'",
                 payload)
        watchdog = ("#!/bin/sh\n"
                    "sleep 90\n"
                    f"test -e {remote}/cancel && exit 0\n"
                    f"echo watchdog-reboot > {remote}/state\n"
                    "exec /sbin/reboot\n")
        step("watchdog_stage", f"cat > {remote}/watchdog.sh; "
             f"chmod 700 {remote}/watchdog.sh; /bin/sh -n {remote}/watchdog.sh",
             watchdog.encode())
        armed = True  # An SSH timeout can occur after the remote process starts.
        step("watchdog_arm", f"/usr/bin/setsid /bin/sh {remote}/watchdog.sh "
             f"</dev/null >{remote}/watchdog.log 2>&1 & "
             f"echo $! > {remote}/pid; sleep 0.1; kill -0 $(cat {remote}/pid)")
        report["state"] = "watchdog-armed"
        save()
        step("firmware_path_set", f"printf '%s' {remote}/firmware > "
             "/sys/module/firmware_class/parameters/path")
        if args.discover:
            controller = subprocess.run(["bluetoothctl", "show"],
                                        capture_output=True, text=True, timeout=6)
            (out / "nexus-controller.txt").write_text(controller.stdout + controller.stderr)
            if controller.returncode or "Powered: yes" not in controller.stdout:
                raise RuntimeError("Nexus Bluetooth controller is not powered")
            if args.connect:
                connector = threading.Thread(target=connect_from_nexus, daemon=True)
                connector.start()
            else:
                scan_file = (out / "nexus-le-scan.txt").open("wb")
                scanner = subprocess.Popen(["bluetoothctl", "--timeout", "25", "scan", "le"],
                                           stdout=scan_file, stderr=subprocess.STDOUT)
            time.sleep(1)
        duration = 30 if args.connect else (18 if args.discover else 0)
        addr_flag = (" --factory-address-hex " + factory_address.replace(":", "")
                     if factory_address else "")
        if args.hciuart_bridge:
            probe_args = (f"--seconds {42 if args.gatt_probe else 20 if args.bluez_query else 10}"
                          f"{' --mask-broken-sync-train' if args.bluez_query else ''}"
                          f" --factory-address-hex {factory_address.replace(':', '')}"
                          if factory_address else
                          f"--seconds {42 if args.gatt_probe else 20 if args.bluez_query else 10}"
                          f"{' --mask-broken-sync-train' if args.bluez_query else ''}")
        else:
            probe_args = (f"--advertise-seconds {duration}"
                          f"{' --connect-observation' if args.connect else ''}{addr_flag}")
        trial_command = ("/usr/bin/unshare -m -- /bin/sh -c 'set -eu; "
                         "mount -t devpts devpts /dev/pts -o newinstance,ptmxmode=0666,mode=0620; "
                         f"exec /usr/bin/python3 {remote}/probe.py {probe_args}'"
                         if args.hciuart_bridge else
                         f"/usr/bin/python3 {remote}/probe.py {probe_args}")
        if args.bluez_query:
            bluez_thread = threading.Thread(target=query_bluez, daemon=True)
            bluez_thread.start()
        if args.gatt_probe:
            gatt_thread = threading.Thread(target=query_gatt, daemon=True)
            gatt_thread.start()
            nexus_thread = threading.Thread(target=query_nexus_ping, daemon=True)
            nexus_thread.start()
        raw = step("hci_probe", f"/usr/bin/timeout -k 2 {55 if args.gatt_probe else 45 if args.discover else 25} "
                   + trial_command,
                   timeout=62 if args.gatt_probe else 52 if args.discover else 32)
        report["probe"] = json.loads(raw)
        expected_state = "bridge-complete" if args.hciuart_bridge else "hci-commands-complete"
        if report["probe"]["state"] != expected_state:
            raise RuntimeError("HCI probe reported failure")
        if bluez_thread is not None:
            bluez_thread.join(timeout=2)
            if bluez_thread.is_alive():
                raise RuntimeError("BlueZ query did not finish")
            report["bluez_query"] = bluez_results
            if (bluez_results.get("exit") != 0 or not bluez_results.get("controller_seen") or
                    not bluez_results.get("factory_identity_seen") or
                    (args.bluez_power and not bluez_results.get("powered"))):
                raise RuntimeError("BlueZ did not report the temporary controller")
        if gatt_thread is not None:
            gatt_thread.join(timeout=3)
            report["gatt_probe"] = gatt_results
            if gatt_thread.is_alive() or gatt_results.get("exit") != 0 or \
                    not gatt_results.get("registered"):
                raise RuntimeError("GATT application did not register and exit cleanly")
        if nexus_thread is not None:
            nexus_thread.join(timeout=3)
            report["nexus_gatt_ping"] = nexus_results
            if nexus_thread.is_alive() or nexus_results.get("state") != "ping-info-complete":
                raise RuntimeError("Nexus did not complete a GATT PING/INFO")
        if scanner is not None:
            try:
                report["nexus_scan_exit"] = scanner.wait(timeout=28)
            except subprocess.TimeoutExpired:
                scanner.terminate()
                report["nexus_scan_exit"] = scanner.wait(timeout=5)
                report["nexus_scan_timed_out"] = True
            scan_file.close()
            scan_file = None
            scan = (out / "nexus-le-scan.txt").read_text(errors="replace")
            addr_hex = next((item["reply_hex"] for item in report["probe"]["commands"]
                             if item["name"] == "read_bd_address"), "")
            address = (":".join(f"{part:02X}" for part in bytes.fromhex(addr_hex)[::-1])
                       if len(addr_hex) == 12 else "")
            report["lynx_address"] = address
            report["nexus_saw_lynx_address"] = bool(address) and address in scan.upper()
            report["nexus_saw_lynx_name"] = "Lynx" in scan
        if connector is not None:
            connector.join(timeout=2)
            if connector.is_alive():
                raise RuntimeError("Nexus connector did not finish")
            report["nexus_connection"] = connect_results
            scan = (out / "nexus-le-scan.txt").read_text(errors="replace")
            report["nexus_saw_lynx_address"] = (factory_address or "00:00:46:67:61:01") in scan.upper()
            report["nexus_saw_lynx_name"] = "Lynx" in scan
        after = json.loads(step("health_after", "/usr/local/bin/lynx-status --assert-ready"))
        if after["boot_id"] != identity[0] or after["issues"] or not after["wifi"]["carrier"]:
            raise RuntimeError("Alpine health changed during BT probe")
        step("kernel_log", "dmesg | tail -n 150")
        report["state"] = "hci-commands-complete-healthy"
    except Exception as exc:
        report.update(state="failed-or-contact-lost", error=str(exc))
    finally:
        if scanner is not None and scanner.poll() is None:
            scanner.terminate()
            try:
                scanner.wait(timeout=3)
            except subprocess.TimeoutExpired:
                scanner.kill()
                scanner.wait(timeout=3)
        if scan_file is not None:
            scan_file.close()
        if args.discover:
            try:
                subprocess.run(["bluetoothctl", "scan", "off"],
                               capture_output=True, timeout=6)
            except (OSError, subprocess.TimeoutExpired):
                pass
        if args.bluez_query:
            try:
                stopped = phone("rc-service bluetooth stop; rc-service dbus stop; "
                                "! rc-service bluetooth status >/dev/null 2>&1; "
                                "! rc-service dbus status >/dev/null 2>&1", timeout=15)
                report["bluez_services_stopped"] = stopped.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                report["bluez_services_stopped"] = False
        if firmware_path:
            try:
                restored = phone(f"printf '%s' {firmware_path} > "
                                 "/sys/module/firmware_class/parameters/path; "
                                 f'test "$(cat /sys/module/firmware_class/parameters/path)" = {firmware_path}',
                                 timeout=8)
                report["firmware_path_restored"] = restored.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                report["firmware_path_restored"] = False
        probe_returned = any(item["name"] == "hci_probe" and item.get("exit") in (0, 1)
                             for item in report["steps"])
        if armed and probe_returned and report.get("firmware_path_restored") and \
                report.get("bluez_services_stopped", True):
            try:
                safe = phone("/usr/local/bin/lynx-status --assert-ready", timeout=8)
                healthy = safe.returncode == 0 and not json.loads(safe.stdout)["issues"] and \
                    json.loads(safe.stdout)["boot_id"] == report.get("boot_id")
                if healthy:
                    cancelled = phone(f"touch {remote}/cancel; test -e {remote}/cancel", timeout=8)
                    report["watchdog_cancelled"] = cancelled.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                report["watchdog_cancelled"] = False
        if armed and not report.get("watchdog_cancelled"):
            report["watchdog_reboot_expected_within_seconds"] = 90
        report["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
        report["ended_monotonic_ns"] = time.monotonic_ns()
        save()
    print(json.dumps({"state": report["state"], "receipt": str(out / "result.json"),
                      "watchdog_cancelled": report.get("watchdog_cancelled"),
                      "error": report.get("error")}))
    if report["state"] != "hci-commands-complete-healthy" or not report.get("watchdog_cancelled"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
