"""Offline unit tests for extended Lynx senses: light, proximity, network, hearing."""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent          # lynx/senses
REPO = HERE.parents[1]                          # /noobia
AUTONOMY_DIR = REPO / "common" / "autonomy"


def _load(name: str, rel: str):
    path = HERE / rel
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


lib = _load("lynx_senses_lib", "common/lynx_senses_lib.py")
light = _load("lynx_sense_light", "light/lynx_sense_light.py")
proximity = _load("lynx_sense_proximity", "proximity/lynx_sense_proximity.py")
network = _load("lynx_sense_network", "network/lynx_sense_network.py")
hearing = _load("lynx_sense_hearing", "hearing/lynx_sense_hearing.py")
security = _load("lynx_sense_security", "security/lynx_sense_security.py")


def _real_sense_module():
    spec = importlib.util.spec_from_file_location("noobia_sense_real", AUTONOMY_DIR / "sense.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RecordingSense:
    def __init__(self, real):
        self._real = real
        self.emits = []

    def format_line(self, *a, **k):
        return self._real.format_line(*a, **k)

    def emit(self, *a, **k):
        self.emits.append((a, k))
        return self._real.format_line(*a, **k)


class ExtendedSensesCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="lynx-ext-senses-")
        self.state_dir = Path(self._tmp.name)
        self._saved_autonomy_dir = os.environ.get("NOOBIA_AUTONOMY_DIR")
        os.environ["NOOBIA_AUTONOMY_DIR"] = str(AUTONOMY_DIR)
        os.environ["NOOBIA_SENSES_STATE_DIR"] = str(self.state_dir)
        self.recorder = RecordingSense(_real_sense_module())
        for mod in (lib, light, proximity, network, hearing, security):
            mod.import_sense = lambda: self.recorder

    def tearDown(self):
        self._tmp.cleanup()
        if self._saved_autonomy_dir is not None:
            os.environ["NOOBIA_AUTONOMY_DIR"] = self._saved_autonomy_dir

    def test_light_transitions(self):
        # Sample 1: Baseline (dark)
        res, code = light.run(reader=lambda: {"raw": [1, 0, 0]})
        self.assertEqual(code, 0)
        self.assertEqual(len(self.recorder.emits), 0)

        # Sample 2: Transition to bright
        res, code = light.run(reader=lambda: {"raw": [10, 0, 0]})
        self.assertEqual(code, 0)
        self.assertEqual(len(self.recorder.emits), 1)
        self.assertEqual(self.recorder.emits[0][0][1], "light")
        self.assertEqual(self.recorder.emits[0][0][2], "bright")

        # Sample 3: Transition back to dark
        res, code = light.run(reader=lambda: {"raw": [1, 0, 0]})
        self.assertEqual(code, 0)
        self.assertEqual(len(self.recorder.emits), 2)
        self.assertEqual(self.recorder.emits[1][0][1], "light")
        self.assertEqual(self.recorder.emits[1][0][2], "dark")

    def test_light_self_caused_by_flashlight(self):
        # Baseline dark
        light.run(reader=lambda: {"raw": [1, 0, 0]})
        
        # Transition to bright with recent flashlight
        os.environ["LYNX_FLASHLIGHT_RECENT"] = "1"
        try:
            res, code = light.run(reader=lambda: {"raw": [10, 0, 0]})
            self.assertEqual(code, 0)
            self.assertEqual(len(self.recorder.emits), 1)
            self.assertEqual(self.recorder.emits[0][1]["fields"].get("cause"), "self")
        finally:
            os.environ.pop("LYNX_FLASHLIGHT_RECENT", None)

    def test_proximity_transitions(self):
        # Sample 1: Baseline (far)
        res, code = proximity.run(reader=lambda: {"raw": [0, 1023, 0]})
        self.assertEqual(code, 0)
        self.assertEqual(len(self.recorder.emits), 0)

        # Sample 2: Transition to near
        res, code = proximity.run(reader=lambda: {"raw": [1, 400, 0]})
        self.assertEqual(code, 0)
        self.assertEqual(len(self.recorder.emits), 1)
        self.assertEqual(self.recorder.emits[0][0][1], "proximity")
        self.assertEqual(self.recorder.emits[0][0][2], "near")

        # Sample 3: Transition to far
        res, code = proximity.run(reader=lambda: {"raw": [0, 1000, 0]})
        self.assertEqual(code, 0)
        self.assertEqual(len(self.recorder.emits), 2)
        self.assertEqual(self.recorder.emits[1][0][1], "proximity")
        self.assertEqual(self.recorder.emits[1][0][2], "far")

    def test_network_device_seen_and_lost(self):
        # Sample 1: Baseline
        res, code = network.run(reader=lambda: {"192.168.100.1": "00:11:22:33:44:55"})
        self.assertEqual(code, 0)
        self.assertEqual(len(self.recorder.emits), 0)

        # Sample 2: New device seen
        res, code = network.run(reader=lambda: {
            "192.168.100.1": "00:11:22:33:44:55",
            "192.168.100.106": "40:a5:ef:5f:66:f1"
        })
        self.assertEqual(code, 0)
        self.assertEqual(len(self.recorder.emits), 1)
        self.assertEqual(self.recorder.emits[0][0][1], "network")
        self.assertEqual(self.recorder.emits[0][0][2], "device.seen")
        self.assertEqual(self.recorder.emits[0][1]["fields"]["ip"], "192.168.100.106")

        # Sample 3: Device lost
        res, code = network.run(reader=lambda: {"192.168.100.106": "40:a5:ef:5f:66:f1"})
        self.assertEqual(code, 0)
        self.assertEqual(len(self.recorder.emits), 2)
        self.assertEqual(self.recorder.emits[1][0][1], "network")
        self.assertEqual(self.recorder.emits[1][0][2], "device.lost")
        self.assertEqual(self.recorder.emits[1][1]["fields"]["ip"], "192.168.100.1")

    def test_hearing_sound_detected(self):
        # Sample 0: Disabled by default
        res, code = hearing.run(reader=lambda: {"captured": True, "late_rms": 3.0, "late_peak": 10}, enabled=False)
        self.assertEqual(code, 0)
        self.assertFalse(res.get("enabled"))
        self.assertEqual(len(self.recorder.emits), 0)

        # Sample 1: Baseline silence (enabled)
        res, code = hearing.run(reader=lambda: {"captured": True, "late_rms": 3.0, "late_peak": 10}, enabled=True)
        self.assertEqual(code, 0)
        self.assertEqual(len(self.recorder.emits), 0)

        # Sample 2: Sound heard (peak 150)
        res, code = hearing.run(reader=lambda: {"captured": True, "late_rms": 35.0, "late_peak": 150}, enabled=True)
        self.assertEqual(code, 0)
        self.assertEqual(len(self.recorder.emits), 1)
        self.assertEqual(self.recorder.emits[0][0][1], "hearing")
        self.assertEqual(self.recorder.emits[0][0][2], "sound.heard")

    def test_security_sense_integration(self):
        journal_file = str(self.state_dir / "security.jsonl")
        unexpected_sockets = [
            {"proto": "tcp", "ip": "192.168.100.107", "port": 2222, "inode": "1001"},
            {"proto": "tcp", "ip": "0.0.0.0", "port": 9999, "inode": "2002"},
        ]
        res, code = security.run(
            now=1000,
            journal_file=journal_file,
            dropbear_logs=[],
            socket_reader=lambda: unexpected_sockets,
            rate_reader=lambda: {},
            auth_reader=lambda l, o: ([], o),
            hash_reader=lambda: {},
        )
        self.assertEqual(code, 0)
        self.assertEqual(res["emitted_count"], 1)
        self.assertEqual(self.recorder.emits[0][0][1], "security")
        self.assertEqual(self.recorder.emits[0][0][2], "intrusion.suspected")
        self.assertEqual(int(self.recorder.emits[0][1]["fields"]["port"]), 9999)


if __name__ == "__main__":
    unittest.main()
