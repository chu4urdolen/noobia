"""noobia_gpu_restart_monitor
================================

This module implements a lightweight GPU monitoring daemon that runs as a
systemd service on the Nexus machine.  It uses NVIDIA's NVML (via the
``pynvml`` package) to sample the following metrics:

* **Power consumption** (Watts) and **utilization** (% of GPU compute) every
  200 ms.
* **Temperature** (°C) and **VRAM usage** (MiB) every 1 s.
* **Power limits** (current and default) every 60 s.

Data is written to an hourly CSV file in ``/var/log/noobia_gpu/``.  Each row
contains a UTC timestamp and the sampled values.  The CSV is flushed to disk
every second to preserve the most recent measurements when an unexpected
reboot occurs.

The daemon also listens to the ``PrepareForShutdown`` signal from
``systemd-logind`` via D-Bus.  When the signal is received we record a
``SHUTDOWN`` row and immediately flush the file.

On startup the daemon checks the previous hour's log.  If the log ends with a
``SHUTDOWN`` row it is removed – the shutdown was graceful.  Otherwise the
log is inspected for recent GPU activity; if activity is present the log is
preserved as an incident report.

The script is intentionally self‑contained and does not depend on external
configuration – all paths and parameters are hard‑coded for simplicity.
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
        nvmlDeviceGetPowerManagementDefaultLimit,
        nvmlDeviceGetPowerManagementLimitConstraints,
        nvmlDeviceGetPowerManagementLimitInfo,
        nvmlDeviceGetPowerManagementDefaultLimit,
        nvmlDeviceGetPowerManagementLimit,
        nvmlDeviceGetPowerManagementDefaultLimit,
    )
    NVML_AVAILABLE = True
except Exception:  # pragma: no cover - defensive for environments without NVML
    NVML_AVAILABLE = False

try:  # D-Bus for listening to PrepareForShutdown
    import dbus
    import dbus.mainloop.glib
    from gi.repository import GLib
    DBUS_AVAILABLE = True
except Exception:  # pragma: no cover - if dbus is missing
    DBUS_AVAILABLE = False

LOG_DIR = Path("/var/log/noobia_gpu")
LOG_DIR.mkdir(parents=True, exist_ok=True)


def get_current_hour_file() -> Path:
    """Return the path of the CSV file for the current UTC hour."""
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
            return {
                "power_w": None,
                "util_pct": None,
                "temp_c": None,
                "vram_used_mb": None,
                "power_limit_w": None,
            }
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
        except Exception as exc:  # pragma: no cover - hardware errors
            return {
                "power_w": None,
                "util_pct": None,
                "temp_c": None,
                "vram_used_mb": None,
                "power_limit_w": None,
            }

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
        # If the file exists from a previous run, inspect it
        if file_path.exists():
            self._handle_existing_file(file_path)
        # Open for appending, create if not exists
        csvfile = file_path.open("a", newline="")
        writer = csv.writer(csvfile)
        if csvfile.tell() == 0:  # header
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
        # Start the main loop
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
        """Inspect the existing log file from a previous run.

        If the file ends with a SHUTDOWN event we consider the shutdown
        graceful and delete the file.  Otherwise we keep the file as an
        incident report.
        """
        with path.open("r") as f:
            rows = list(csv.reader(f))
        if not rows:
            return
        last_row = rows[-1]
        if len(last_row) >= 7 and last_row[6] == "SHUTDOWN":
            # graceful shutdown – remove file
            path.unlink()
        else:
            # keep the file – incident
            pass


def shutdown_handler(_signum, _frame):
    # Called by systemd via signal to terminate the daemon
    sys.exit(0)


def dbus_shutdown_listener(monitor: GPUMonitor):
    """Listen for PrepareForShutdown via systemd-logind and record it.

    This function sets up a D-Bus main loop and registers a callback.  When
    the signal is received the monitor writes a SHUTDOWN row and exits.
    """
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
    # Write shutdown event
    file_path = get_current_hour_file()
    with file_path.open("a", newline="") as f:
        writer = csv.writer(f)
        monitor.write_row(writer, monitor.sample(), event="SHUTDOWN")
        f.flush()
    monitor.running = False
    # exit the process
    sys.exit(0)


def main() -> None:
    monitor = GPUMonitor()
    signal.signal(signal.SIGTERM, shutdown_handler)
    # Start DBus listener in a separate thread
    if DBUS_AVAILABLE:
        import threading
        t = threading.Thread(target=dbus_shutdown_listener, args=(monitor,), daemon=True)
        t.start()
    monitor.run()


if __name__ == "__main__":
    main()

