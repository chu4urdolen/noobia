"""Unit tests for :mod:`mag_read`.

The tests exercise the real ``read_mag`` function while mocking all external
dependencies: ``Path.is_char_device``, ``Path.read_text`` and
``subprocess.run``.  Four scenarios are verified:

1. **Valid sample** – ``disabled: true`` and correct sensor info – should
   return the expected raw values.
2. **Invalid disabled flag** – ``disabled: false`` should raise
   :class:`RuntimeError`.
3. **Wrong sensor name** – sample with a mismatched ``info.name`` should
   raise :class:`RuntimeError`.
4. **Non‑integer axis** – a sample where ``raw_xyz`` contains a float should
   raise :class:`RuntimeError`.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from projects.lynx_magnetometer.mag_read import read_mag


class TestMagRead(TestCase):
    def setUp(self) -> None:  # pragma: no cover
        self.p1 = patch.object(Path, "is_char_device", return_value=True)
        self.p2 = patch.object(Path, "read_text", return_value="akm09918 mag")
        self.p1.start(); self.p2.start()

    def tearDown(self) -> None:  # pragma: no cover
        patch.stopall()

    def _mock_run(self, stdout: str):
        class _Completed:
            def __init__(self, out):
                self.returncode = 0
                self.stdout = out

        return patch("subprocess.run", return_value=_Completed(stdout))

    def test_valid(self):
        sample = {
            "sensor_type": 2,
            "disabled": True,
            "info": {"name": "akm09918 mag", "gain": 1000},
            "events": [
                {"raw_xyz": [1, 2, 3]},
                {"raw_xyz": [4, 5, 6]},
                {"raw_xyz": [7, 8, 9]},
            ],
        }
        with self._mock_run(json.dumps(sample)):
            result = read_mag()
        self.assertEqual(result["raw"], [7, 8, 9])
        self.assertTrue(result["sensor_disabled_after_sample"])

    def test_invalid_disabled(self):
        sample = {
            "sensor_type": 2,
            "disabled": False,
            "info": {"name": "akm09918 mag", "gain": 1000},
            "events": [
                {"raw_xyz": [1, 2, 3]},
                {"raw_xyz": [4, 5, 6]},
                {"raw_xyz": [7, 8, 9]},
            ],
        }
        with self._mock_run(json.dumps(sample)):
            with self.assertRaises(RuntimeError):
                read_mag()

    def test_wrong_name(self):
        sample = {
            "sensor_type": 2,
            "disabled": True,
            "info": {"name": "wrong", "gain": 1000},
            "events": [
                {"raw_xyz": [1, 2, 3]},
                {"raw_xyz": [4, 5, 6]},
                {"raw_xyz": [7, 8, 9]},
            ],
        }
        with self._mock_run(json.dumps(sample)):
            with self.assertRaises(RuntimeError):
                read_mag()

    def test_noninteger_axis(self):
        sample = {
            "sensor_type": 2,
            "disabled": True,
            "info": {"name": "akm09918 mag", "gain": 1000},
            "events": [
                {"raw_xyz": [1, 2, 3]},
                {"raw_xyz": [4, 5, 6]},
                {"raw_xyz": [7.0, 8, 9]},
            ],
        }
        with self._mock_run(json.dumps(sample)):
            with self.assertRaises(RuntimeError):
                read_mag()

    def test_single_event(self):
        """The helper may return only one event; ensure it is accepted.

        The returned raw values should be from that single event.
        """
        sample = {
            "sensor_type": 2,
            "disabled": True,
            "info": {"name": "akm09918 mag", "gain": 1000},
            "events": [{"raw_xyz": [10, 20, 30]}],
        }
        with self._mock_run(json.dumps(sample)):
            result = read_mag()
        self.assertEqual(result["raw"], [10, 20, 30])
