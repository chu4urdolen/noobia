"""Offline fixture checks for peripheral status semantics."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from lynx_peripheral_status import inventory


class PeripheralStatusTest(unittest.TestCase):
    def test_empty_tree_remains_unvalidated(self):
        with TemporaryDirectory() as temp:
            state = inventory(Path(temp))
        self.assertEqual(set(state), {"nfc", "fingerprint", "headset"})
        self.assertFalse(any(item["validated"] for item in state.values()))
        self.assertFalse(any(item["interface_ready"] for item in state.values()))

    def test_headset_switches_and_nfc_node_are_only_interface_evidence(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ("sys/class/input/event1/device", "dev/input",
                         "sys/bus/platform/devices/odm:nfc_chipset/driver", "dev"):
                (root / name).mkdir(parents=True, exist_ok=True)
            (root / "sys/class/input/event1/device/name").write_text("mt6983-mt6338 Headset Jack\n")
            (root / "dev/input/event1").touch()
            (root / "dev/nq-nci").touch()
            state = inventory(root, lambda path: (1 << 2) | (1 << 7))
        self.assertTrue(state["headset"]["interface_ready"])
        self.assertTrue(state["headset"]["evidence"]["switches"]["headphone"])
        self.assertFalse(state["headset"]["evidence"]["switches"]["microphone"])
        self.assertTrue(state["nfc"]["interface_ready"])
        self.assertFalse(state["headset"]["validated"])
        self.assertFalse(state["nfc"]["validated"])

    def test_failed_headset_read_is_not_ready(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            event = root / "sys/class/input/event1/device"
            event.mkdir(parents=True)
            (event / "name").write_text("mt6983-mt6338 Headset Jack\n")
            def fail(_path):
                raise PermissionError("test")
            state = inventory(root, fail)
        self.assertFalse(state["headset"]["interface_ready"])
        self.assertEqual(state["headset"]["evidence"]["switch_read_error"], "PermissionError")


if __name__ == "__main__":
    unittest.main()
