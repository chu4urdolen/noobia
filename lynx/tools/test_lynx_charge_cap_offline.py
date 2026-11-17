#!/usr/bin/env python3
"""Exercise charge-cap state transitions with temporary fake sysfs files."""

from pathlib import Path
import re
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "linux-port/lynx-charge-cap.sh"


def main():
    source = SOURCE.read_text()
    assert not re.search(r"^\s*(?:/sbin/)?(?:poweroff|reboot|openrc-shutdown)\b",
                         source, re.M)
    assert "STOP_AT=98" in source and "RESUME_AT=95" in source
    with tempfile.TemporaryDirectory(prefix="lynx-charge-cap-") as temp:
        root = Path(temp)
        gauge = root / "battery_snapshot"
        status = root / "status"
        state_dir = root / "run"
        state_dir.mkdir()
        status.write_text("Charging\n")
        candidate = source.replace(
            "GAUGE=/sys/bus/i2c/devices/7-0055/battery_snapshot",
            f"GAUGE={gauge}").replace(
            "STATUS=/sys/class/power_supply/11e01000.i2c:mt6375@34:chg/status",
            f"STATUS={status}").replace(
            "STATE=/run/lynx/charge-cap",
            f"STATE={state_dir / 'charge-cap'}").replace(
            "[ -d /run/lynx ]", f"[ -d {state_dir} ]")
        script = root / "controller.sh"
        script.write_text(candidate)

        def sample(capacity, temperature=30000, valid=True):
            gauge.write_text(
                "gauge_device_type=42495\n"
                f"capacity_error={0 if valid else 1}\n"
                "temperature_error=0\n"
                f"capacity_percent={capacity}\n"
                f"temperature_millidegrees_celsius={temperature}\n")

        def apply():
            return subprocess.run(["busybox", "sh", str(script), "--apply-once", "--armed"],
                                  capture_output=True, text=True, timeout=5)

        sample(97)
        assert apply().returncode == 0 and status.read_text() == "Charging\n"
        sample(98)
        assert apply().returncode == 0 and status.read_text() == "0\n"
        assert (state_dir / "charge-cap").read_text() == "stopped\n"
        sample(96)
        assert apply().returncode == 0 and status.read_text() == "0\n"
        sample(95, 39000)
        assert apply().returncode == 0 and status.read_text() == "0\n"
        sample(95, 30000)
        assert apply().returncode == 0 and status.read_text() == "1\n"
        assert (state_dir / "charge-cap").read_text() == "charging\n"
        sample(99, valid=False)
        assert apply().returncode != 0 and status.read_text() == "1\n"
        print("charge-cap fixture transitions passed; no hardware contacted")


if __name__ == "__main__":
    main()
