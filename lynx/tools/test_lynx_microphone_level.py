"""Verify the one-second capture restores the mixer after a recording failure."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import lynx_microphone_level as microphone


class MicrophoneRestorationTest(unittest.TestCase):
    def test_capture_failure_restores_both_route_controls(self):
        controls = dict(microphone.BASELINE)
        with TemporaryDirectory() as directory, \
             patch.object(microphone, "LOCK", Path(directory) / "microphone.lock"), \
             patch.object(microphone, "guarded_health", return_value="test-boot"), \
             patch.object(microphone, "value", side_effect=lambda n: controls[n]), \
             patch.object(microphone, "set_value", side_effect=lambda n, v: controls.__setitem__(n, v)), \
             patch.object(microphone, "run", side_effect=RuntimeError("arecord failed")):
            with self.assertRaisesRegex(RuntimeError, "arecord failed"):
                microphone.sample_level()
        self.assertEqual(controls, microphone.BASELINE)

    def test_partial_route_failure_also_restores_mixer(self):
        controls = dict(microphone.BASELINE)

        def set_value(numid, number):
            controls[numid] = number
            if numid == 50 and number == 1:
                raise RuntimeError("route failed after write")

        with TemporaryDirectory() as directory, \
             patch.object(microphone, "LOCK", Path(directory) / "microphone.lock"), \
             patch.object(microphone, "guarded_health", return_value="test-boot"), \
             patch.object(microphone, "value", side_effect=lambda n: controls[n]), \
             patch.object(microphone, "set_value", side_effect=set_value):
            with self.assertRaisesRegex(RuntimeError, "route failed after write"):
                microphone.sample_level()
        self.assertEqual(controls, microphone.BASELINE)


if __name__ == "__main__":
    unittest.main()
