#!/usr/bin/env python3
"""Bluetooth service supervisor with radio-order and firmware checks.

Run inside a private mount namespace. Keep existing Wi-Fi/SSH independent.
Only the diagnostic PING/INFO GATT endpoint is started.
"""

import hashlib
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import time


KERNEL = "5.10.149-android12-9-o-g311738fbb5a8"
ROOT = Path("/usr/local/share/lynx-bluetooth")
MANIFEST = ROOT / "firmware-sha256.json"
FIRMWARE = Path("/vendor/firmware")
RUNTIME = Path("/run/lynx/bluetooth")
GATT = Path("/usr/local/bin/lynx-ble-gatt")
BRIDGE = Path("/usr/local/bin/lynx-bt-hciuart")
PYTHON = "/usr/bin/python3"


def run(command, timeout=10):
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"command failed: {command[0]} ({result.returncode})")
    return result.stdout


def event(name, **fields):
    print(json.dumps({"event": name, "at": int(time.time()), **fields}), flush=True)


def radio_boot_order(log):
    """Require BT registration and a calibration settle period before Wi-Fi."""
    events = (
        "CHECKPOINT_MODULE_OK wlan_drv_gen4m_6983.ko",
        "CHECKPOINT_MODULE_OK btif_drv.ko",
        "CHECKPOINT_MODULE_OK bt_drv_6983.ko",
        "WIFI_STAGE WIFI_STATION_POWER_ON",
    )
    times = {}
    for line in log.splitlines():
        if not line.startswith("LYNX_WIFI uptime="):
            continue
        try:
            stamp, name = line[len("LYNX_WIFI uptime="):].split(" ", 1)
            if name in events:
                if name in times:
                    return False
                times[name] = float(stamp)
        except ValueError:
            return False
    if set(times) != set(events):
        return False
    wlan, btif, bt, station = (times[name] for name in events)
    return 0 < wlan < btif < bt < station and station - bt >= 20


def verify_boot_and_firmware():
    if os.geteuid() != 0:
        raise RuntimeError("root required")
    if run(["uname", "-r"]).strip() != KERNEL:
        raise RuntimeError("Bluetooth modules need the verified kernel ABI")
    loaded = {line.split()[0] for line in Path("/proc/modules").read_text().splitlines()}
    if not {"wlan_drv_gen4m_6983", "btif_drv", "bt_drv_6983"} <= loaded:
        raise RuntimeError("matching Wi-Fi/Bluetooth modules are not loaded")
    if not radio_boot_order(Path("/run/lynx/boot.log").read_text()):
        raise RuntimeError("Bluetooth was not registered before Wi-Fi with a settle period")
    if "PARTNAME=nvdata" not in Path("/sys/class/block/sdc10/uevent").read_text().splitlines():
        raise RuntimeError("nvdata block identity mismatch")
    if Path("/sys/module/firmware_class/parameters/path").read_text().strip() != \
            str(FIRMWARE):
        raise RuntimeError("unexpected firmware search path")
    manifest = json.loads(MANIFEST.read_text())
    if len(manifest) != 7:
        raise RuntimeError("incomplete BT firmware manifest")
    for name, digest in manifest.items():
        if not name.startswith(("BT_FW.", "soc7_0_ram_")) or "/" in name:
            raise RuntimeError("invalid firmware manifest entry")
        with (FIRMWARE / name).open("rb") as source:
            sha = hashlib.file_digest(source, "sha256").hexdigest()
        if sha != digest:
            raise RuntimeError("BT firmware hash mismatch: " + name)
    for path in (GATT, BRIDGE, Path("/usr/local/bin/lynx_bluetooth_hci_probe.py")):
        if not path.is_file() or not os.access(path, os.R_OK):
            raise RuntimeError("missing Bluetooth program: " + str(path))
    if not Path("/run/lynx/noobd.sock").is_socket():
        raise RuntimeError("NRP local socket is unavailable")


def health(min_battery=15):
    status = json.loads(run(["/usr/local/bin/lynx-status", "--assert-ready"], timeout=8))
    if status["issues"] or status["battery"]["capacity_percent"] < min_battery or \
            status["battery"]["temperature_mC"] >= 40000 or \
            status["thermal"]["max_mC"] >= 55000:
        raise RuntimeError("battery, thermal, or Alpine health guard failed")
    return status


def factory_address_file():
    """Read six bytes via no-replay ext4 mount in this private namespace."""
    mountpoint = RUNTIME / "nvdata"
    mountpoint.mkdir(mode=0o700)
    mounted = False
    try:
        run(["mount", "-t", "ext4", "-o", "ro,noload,nosuid,nodev,noexec",
             "/dev/sdc10", str(mountpoint)], timeout=6)
        mounted = True
        address = (mountpoint / "APCFG/APRDEB/BT_Addr").read_bytes()[:6]
        if len(address) != 6 or address == b"\0" * 6 or address[:3] == b"\x00\x00\x46":
            raise RuntimeError("invalid factory Bluetooth address")
        path = RUNTIME / "factory-address"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as target:
            target.write(address)
        return path
    finally:
        if mounted:
            run(["umount", str(mountpoint)], timeout=6)
        mountpoint.rmdir()


def service_running(name):
    return subprocess.run(["rc-service", name, "status"], capture_output=True,
                          timeout=5).returncode == 0


def terminate(process, seconds=5):
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


def supervise():
    stopping = False

    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    bridge = gatt = None
    started_dbus = started_bluez = False
    address_file = None
    RUNTIME.mkdir(mode=0o700, parents=True, exist_ok=True)
    (RUNTIME / "ready").unlink(missing_ok=True)
    try:
        verify_boot_and_firmware()
        health(min_battery=20)
        if service_running("bluetooth"):
            raise RuntimeError("BlueZ is already owned by another service")
        event("preflight-ok")
        address_file = factory_address_file()
        run(["mount", "-t", "devpts", "devpts", "/dev/pts", "-o",
             "newinstance,ptmxmode=0666,mode=0620"], timeout=6)
        bridge_log = (RUNTIME / "bridge.log").open("wb")
        try:
            bridge = subprocess.Popen([PYTHON, str(BRIDGE), "--seconds", "0",
                                       "--mask-broken-sync-train",
                                       "--factory-address-file", str(address_file)],
                                      stdout=bridge_log, stderr=subprocess.STDOUT)
        finally:
            bridge_log.close()
        deadline = time.monotonic() + 10
        while not Path("/sys/class/bluetooth/hci0").exists():
            if stopping or bridge.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError("HCI bridge did not register")
            time.sleep(0.2)
        time.sleep(1)  # Kernel management completes registration after sysfs.
        if not service_running("dbus"):
            run(["rc-service", "dbus", "start"], timeout=10)
            started_dbus = True
        if not service_running("bluetooth"):
            run(["rc-service", "bluetooth", "start"], timeout=12)
            started_bluez = True
        for attempt in range(8):
            if stopping or bridge.poll() is not None:
                raise RuntimeError("startup interrupted")
            powered = subprocess.run(["bluetoothctl", "power", "on"],
                                     capture_output=True, timeout=5)
            if powered.returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("BlueZ did not power controller")
        controller = run(["bluetoothctl", "show"], timeout=5)
        expected = ":".join(f"{byte:02X}" for byte in address_file.read_bytes())
        if f"Controller {expected}" not in controller or "Powered: yes" not in controller:
            raise RuntimeError("BlueZ controller identity or power mismatch")
        run(["bluetoothctl", "pairable", "off"], timeout=5)
        env = dict(os.environ, PYTHONPATH="/usr/local/lib/lynx-bluetooth")
        gatt = subprocess.Popen([PYTHON, str(GATT), "--seconds", "0"],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                env=env, text=True, bufsize=1)
        ready, _, _ = select.select([gatt.stdout], [], [], 10)
        if not ready or gatt.stdout.readline().strip() != "GATT_READY":
            raise RuntimeError("GATT application did not register")
        (RUNTIME / "ready").write_text("ready\n")
        event("ready", controller="hci0", gatt="ping-info")
        next_health = time.monotonic() + 30
        while not stopping:
            if bridge.poll() is not None or gatt.poll() is not None:
                raise RuntimeError("Bluetooth child exited")
            if time.monotonic() >= next_health:
                health()
                next_health = time.monotonic() + 30
            time.sleep(0.5)
        event("stopping")
    finally:
        (RUNTIME / "ready").unlink(missing_ok=True)
        terminate(gatt)
        if started_bluez:
            try:
                subprocess.run(["rc-service", "bluetooth", "stop"],
                               capture_output=True, timeout=10)
            except subprocess.TimeoutExpired:
                event("cleanup-timeout", service="bluetooth")
        if started_dbus:
            try:
                subprocess.run(["rc-service", "dbus", "stop"],
                               capture_output=True, timeout=10)
            except subprocess.TimeoutExpired:
                event("cleanup-timeout", service="dbus")
        terminate(bridge)
        if address_file is not None:
            address_file.unlink(missing_ok=True)
        event("stopped")


if __name__ == "__main__":
    supervise()
