"""Offline interface and validation boundaries for Lynx agent hardware status."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from lynx_platform_status import COMPONENTS, inventory


HEALTH = {
    "battery": {"capacity_percent": 25, "current_mA_signed": 323,
                "temperature_mC": 25200, "voltage_mV": 7630,
                "gauge_type": 42495,
                "read_errors": {"capacity": 0, "current": 0,
                                "temperature": 0, "voltage": 0}},
    "thermal": {"max_mC": 35894, "cooling_states": {"thermal-cpufreq-0": 0}},
    "root_filesystem": {"type": "ext4", "source": "/dev/sdc85",
                        "ext4_errors_count": 0},
    "root_free_mib": 214063,
    "wifi": {"carrier": True, "ipv4": "192.168.100.107/24"},
}


class PlatformStatusTest(unittest.TestCase):
    def test_every_component_is_present_and_unproven_radios_remain_unvalidated(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "dev").mkdir()
            (root / "dev/ccci_0_200").touch()
            (root / "sys/kernel/ccci").mkdir(parents=True)
            (root / "sys/kernel/ccci/boot").write_text(
                "md1:0 | md2:n/a | md3:n/a | md4:n/a | md5:n/a\n")
            (root / "sys/class/udc").mkdir(parents=True)
            (root / "sys/class/udc/dummy_udc.0").touch()
            state = inventory(root, HEALTH)
        self.assertEqual(tuple(state), COMPONENTS)
        for name in ("usb", "cellular", "sim"):
            self.assertFalse(state[name]["validated"], name)
        self.assertFalse(state["usb"]["interface_ready"])
        self.assertTrue(state["cellular"]["interface_ready"])
        self.assertEqual(state["cellular"]["evidence"]["md1_state_code"], 0)
        self.assertFalse(state["sim"]["evidence"]["card_presence_checked"])

    def test_modem_status_reader_does_not_turn_ready_code_into_validation(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            boot = root / "sys/kernel/ccci/boot"
            boot.parent.mkdir(parents=True)
            boot.write_text("md1:4 | md2:n/a\n")
            state = inventory(root, HEALTH)
        self.assertEqual(state["cellular"]["evidence"]["md1_state_code"], 4)
        self.assertFalse(state["cellular"]["validated"])

    def test_live_interfaces_and_health_are_reported_without_controls(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ("sys/module/mediatek_drm", "sys/module/synaptics_tcm2",
                         "sys/module/haptic", "sys/class/leds/vibrator",
                         "dev/dri", "dev/input", "dev/snd", "proc/asound"):
                (root / name).mkdir(parents=True, exist_ok=True)
            for name in ("dev/dri/card0", "dev/input/event1", "dev/snd/pcmC0D11c",
                         "dev/hf_manager", "proc/hf_manager"):
                (root / name).touch()
            (root / "proc/asound/cards").write_text("0 [mt6983mt6338]\n")
            state = inventory(root, HEALTH)
        for name in ("battery", "thermal", "storage", "wifi", "display",
                     "touch", "audio", "haptic", "sensorhub"):
            self.assertTrue(state[name]["interface_ready"], name)
        for name in ("touch", "audio", "haptic", "sensorhub"):
            self.assertFalse(state[name]["validated"], name)
        self.assertEqual(state["battery"]["evidence"]["current_mA_signed"], 323)
        self.assertEqual(state["touch"]["evidence"]["input_event_nodes"], ["event1"])
        json.dumps(state)  # Whole inventory is JSON serializable.

    def test_bad_health_does_not_turn_storage_or_power_into_success(self):
        with TemporaryDirectory() as temp:
            bad = {**HEALTH,
                   "battery": {**HEALTH["battery"], "read_errors":
                               {**HEALTH["battery"]["read_errors"], "current": 1}},
                   "root_filesystem": {**HEALTH["root_filesystem"],
                                       "ext4_errors_count": 2}}
            state = inventory(Path(temp), bad)
        self.assertFalse(state["battery"]["validated"])
        self.assertFalse(state["storage"]["validated"])


if __name__ == "__main__":
    unittest.main()
