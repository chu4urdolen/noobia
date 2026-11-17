#!/usr/bin/env python3
"""Install the V52 Bluetooth candidate as passive files; never start/enable it."""

import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import time

from lynx_wifi_v19_contact import ssh_command


ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
FIRMWARE = ROOT / "linux-port/artifacts/stock-cph2493-August-eu-ota/wifi-reference/vendor-unpacked/firmware"
MANIFEST = json.loads((TOOLS / "lynx-bt-firmware-sha256.json").read_text())
BOOT_SHA = "9206aafb339ad66b2d942ea5795b8f476a5eaf3a148f9cdfc76be22cb83e30bf"
PROGRAMS = {
    "lynx-bluetoothd": "lynx_bluetoothd.py",
    "lynx-bt-hciuart": "lynx_stpbt_hciuart_bridge.py",
    "lynx_bluetooth_hci_probe.py": "lynx_bluetooth_hci_probe.py",
    "lynx-ble-gatt": "lynx_ble_gatt_probe.py",
}


def phone(command, payload=None, timeout=20):
    argv = ssh_command("192.168.100.107", command)
    argv[-2:-2] = ["-p", "2222"]
    return subprocess.run(argv, input=payload, capture_output=True, timeout=timeout)


def main():
    receipt_dir = ROOT / "logs" / f"v52-bluetooth-install-{time.time_ns()}"
    receipt_dir.mkdir(mode=0o700)
    remote = "/run/lynx-bluetooth-install-" + str(time.time_ns())
    report = {"state": "preflight", "remote": remote,
              "boot_partition_writes": False, "service_started": False,
              "service_enabled": False, "steps": []}

    def save():
        temporary = receipt_dir / "result.tmp"
        temporary.write_text(json.dumps(report, indent=2) + "\n")
        temporary.replace(receipt_dir / "result.json")

    def step(name, command, payload=None, timeout=20):
        start = time.monotonic_ns()
        result = phone(command, payload, timeout)
        (receipt_dir / (name + ".stdout")).write_bytes(result.stdout)
        (receipt_dir / (name + ".stderr")).write_bytes(result.stderr)
        report["steps"].append({"name": name, "exit": result.returncode,
                                "started_monotonic_ns": start,
                                "ended_monotonic_ns": time.monotonic_ns()})
        save()
        if result.returncode:
            raise RuntimeError(name + " failed")
        return result.stdout.decode(errors="replace")

    save()
    try:
        identity = step("identity", "cat /proc/sys/kernel/random/boot_id; "
                        "sha256sum /dev/sdc39 | cut -c1-64").splitlines()
        if len(identity) != 2 or identity[1] != BOOT_SHA:
            raise RuntimeError("Lynx is not on exact V52")
        report["boot_id"] = identity[0]
        before = json.loads(step("health_before", "/usr/local/bin/lynx-status --assert-ready"))
        if before["issues"] or before["battery"]["capacity_percent"] < 40 or \
                before["thermal"]["max_mC"] >= 45000:
            raise RuntimeError("phone health preflight failed")
        step("destinations_empty", "set -eu; apk info -e bluez; "
             "! rc-service bluetooth status >/dev/null 2>&1; "
             "! rc-service dbus status >/dev/null 2>&1; "
             "for p in /vendor/firmware /usr/local/lib/lynx-bluetooth "
             "/usr/local/share/lynx-bluetooth /usr/local/bin/lynx-bluetoothd "
             "/usr/local/bin/lynx-bt-hciuart /usr/local/bin/lynx_bluetooth_hci_probe.py "
             "/usr/local/bin/lynx-ble-gatt /etc/init.d/lynx-bluetooth; "
             "do test ! -e \"$p\"; done")
        for name, digest in MANIFEST.items():
            if hashlib.sha256((FIRMWARE / name).read_bytes()).hexdigest() != digest:
                raise RuntimeError("local stock firmware hash mismatch: " + name)
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode="w:gz") as tar:
            for name in MANIFEST:
                tar.add(FIRMWARE / name, arcname="firmware/" + name)
            for target, source in PROGRAMS.items():
                tar.add(TOOLS / source, arcname="programs/" + target)
            tar.add(TOOLS / "lynx-bt-firmware-sha256.json", arcname="firmware-sha256.json")
            tar.add(TOOLS / "lynx-bluetooth-openrc.sh", arcname="lynx-bluetooth-openrc")
            tar.add(TOOLS / "vendor_dbus_next/dbus_next", arcname="vendor/dbus_next",
                    filter=lambda item: None if "__pycache__" in item.name else item)
        payload = archive.getvalue()
        report["archive_sha256"] = hashlib.sha256(payload).hexdigest()
        report["archive_bytes"] = len(payload)
        step("stage", f"mkdir -m 700 {remote}; cat > {remote}/bundle.tar.gz; "
             f'test "$(sha256sum {remote}/bundle.tar.gz | cut -c1-64)" = '
             f"{report['archive_sha256']}; tar -xzf {remote}/bundle.tar.gz -C {remote}",
             payload, timeout=25)
        installer = (TOOLS / "lynx_bluetooth_install_on_phone.py").read_bytes()
        installer_sha = hashlib.sha256(installer).hexdigest()
        step("installer_stage", f"cat > {remote}/install.py; "
             f'test "$(sha256sum {remote}/install.py | cut -c1-64)" = {installer_sha}; '
             f"/usr/bin/python3 -m py_compile {remote}/install.py", installer)
        install_output = step("install", f"/usr/bin/python3 {remote}/install.py {remote}",
                              timeout=30)
        report["phone_install"] = json.loads(install_output)
        if report["phone_install"].get("state") != "passive-files-installed":
            raise RuntimeError("phone installer did not confirm passive state")
        step("installed_validate", "set -eu; "
             "PYTHONPATH=/usr/local/lib/lynx-bluetooth /usr/bin/python3 -m py_compile "
             "/usr/local/bin/lynx-bluetoothd /usr/local/bin/lynx-bt-hciuart "
             "/usr/local/bin/lynx_bluetooth_hci_probe.py /usr/local/bin/lynx-ble-gatt; "
             "/bin/sh -n /etc/init.d/lynx-bluetooth")
        after = json.loads(step("health_after", "/usr/local/bin/lynx-status --assert-ready"))
        if after["boot_id"] != identity[0] or after["issues"]:
            raise RuntimeError("Alpine health changed after passive file install")
        step("service_disabled", "set -eu; ! rc-service lynx-bluetooth status >/dev/null 2>&1; "
             "! rc-update show default | grep -q lynx-bluetooth; "
             "! rc-update show boot | grep -q lynx-bluetooth")
        report["state"] = "installed-disabled-healthy"
    except Exception as exc:
        report.update(state="failed", error=str(exc))
    finally:
        save()
    print(json.dumps({"state": report["state"],
                      "receipt": str(receipt_dir / "result.json"),
                      "error": report.get("error")}))
    if report["state"] != "installed-disabled-healthy":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
