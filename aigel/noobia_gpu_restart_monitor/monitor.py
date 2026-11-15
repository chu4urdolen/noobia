"""noobia_gpu_restart_monitor
================================
This is the same implementation as the one in the separate `/noobia/aigel`
directory, but placed under the workspace so it can be committed and
executed from there.
"""
from __future__ import annotations

import csv
import datetime as _dt
import os
import signal
import sys
import time
from pathlib import Path

try:
    from pynvml import (
        nvmlInit,
        nvmlDeviceGetHandleByIndex,
        nvmlDeviceGetPowerUsage,
        nvmlDeviceGetUtilizationRates,
        nvmlDeviceGetTemperature,
        nvmlDeviceGetMemoryInfo,
        nvmlDeviceGetPowerManagementLimit,
    )
    NVML_AVAILABLE = True
except Exception:  # pragma: no cover
    NVML_AVAILABLE = False

try:  # D-Bus for listening to PrepareForShutdown
    import dbus
    import dbus.mainloop.glib
    from gi.repository import GLib
    DBUS_AVAILABLE = True
except Exception:  # pragma: no cover
    DBUS_AVAILABLE = False

LOG_DIR = Path("/var/log/noobia_gpu")
LOG_DIR.mkdir(parents=True, exist_ok=True)


def get_current_hour_file() -> Path:
    ts = _dt.datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    return LOG_DIR / f"{ts.strftime('%Y-%m-%d_%H')}.csv"


class GPUMonitor:
    def __init__(self) -> None:
        self.running = True
        self.last_shutdown = False
        if NVML_AVAILABLE:
            nvmlInit()
            self.device = nvmlDeviceGetHandleByIndex(0)
        else:
            self.device = None

    def sample(self) -> dict:
        if not self.device:
            return {"power_w": None, "util_pct": None, "temp_c": None, "vram_used_mb": None, "power_limit_w": None}
        try:
            power_w = nvmlDeviceGetPowerUsage(self.device) / 1000.0
            util = nvmlDeviceGetUtilizationRates(self.device)
            util_pct = util.gpu
            temp_c = nvmlDeviceGetTemperature(self.device, 0)
            mem = nvmlDeviceGetMemoryInfo(self.device)
            vram_used_mb = mem.used / (1024 * 1024)
            power_limit_w = nvmlDeviceGetPowerManagementLimit(self.device) / 1000.0
            return {
                "power_w": power_w,
                "util_pct": util_pct,
                "temp_c": temp_c,
                "vram_used_mb": vram_used_mb,
                "power_limit_w": power_limit_w,
            }
        except Exception:
            return {"power_w": None, "util_pct": None, "temp_c": None, "vram_used_mb": None, "power_limit_w": None}

    def write_row(self, writer: csv.writer, row: dict, event: str | None = None) -> None:
        ts = _dt.datetime.utcnow().isoformat()
        writer.writerow(
            [
                ts,
                row.get("power_w"),
                row.get("util_pct"),
                row.get("temp_c"),
                row.get("vram_used_mb"),
                row.get("power_limit_w"),
                event,
            ]
        )

    def run(self) -> None:
        file_path = get_current_hour_file()
        if file_path.exists():
            self._handle_existing_file(file_path)
        csvfile = file_path.open("a", newline="")
        writer = csv.writer(csvfile)
        if csvfile.tell() == 0:
            writer.writerow(
                [
                    "timestamp",
                    "power_w",
                    "util_pct",
                    "temp_c",
                    "vram_used_mb",
                    "power_limit_w",
                    "event",
                ]
            )
        last_power_sample = time.time()
        last_temp_sample = time.time()
        last_limit_sample = time.time()
        while self.running:
            now = time.time()
            if now - last_power_sample >= 0.2:
                data = self.sample()
                self.write_row(writer, data)
                csvfile.flush()
                last_power_sample = now
            if now - last_temp_sample >= 1.0:
                data = self.sample()
                self.write_row(writer, data)
                csvfile.flush()
                last_temp_sample = now
            if now - last_limit_sample >= 60.0:
                data = self.sample()
                self.write_row(writer, data)
                csvfile.flush()
                last_limit_sample = now
            time.sleep(0.05)

    def _handle_existing_file(self, path: Path) -> None:
        with path.open("r") as f:
            rows = list(csv.reader(f))
        if not rows:
            return
        last_row = rows[-1]
        if len(last_row) >= 7 and last_row[6] == "SHUTDOWN":
            path.unlink()
        else:
            pass


def shutdown_handler(_signum, _frame):
    sys.exit(0)


def dbus_shutdown_listener(monitor: GPUMonitor):
    if not DBUS_AVAILABLE:
        return
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    bus.add_signal_receiver(
        lambda: shutdown_callback(monitor),
        dbus_interface="org.freedesktop.login1.Manager",
        signal_name="PrepareForShutdown",
    )
    loop = GLib.MainLoop()
    loop.run()


def shutdown_callback(monitor: GPUMonitor) -> None:
    file_path = get_current_hour_file()
    with file_path.open("a", newline="") as f:
        writer = csv.writer(f)
        monitor.write_row(writer, monitor.sample(), event="SHUTDOWN")
        f.flush()
    monitor.running = False
    sys.exit(0)


def main() -> None:
    monitor = GPUMonitor()
    signal.signal(signal.SIGTERM, shutdown_handler)
    if DBUS_AVAILABLE:
        import threading
        t = threading.Thread(target=dbus_shutdown_listener, args=(monitor,), daemon=True)
        t.start()
    monitor.run()


if __name__ == "__main__":
    main()

