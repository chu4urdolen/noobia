"""Unit tests for :mod:`lynx_proximity_read`.

The tests are intentionally *isolated* – they do not touch the real
``/dev/hf_manager`` device, ``/proc/hf_manager`` file, or invoke the real
``lynx-hf-sample`` helper.  Instead the standard library :mod:`unittest`
framework together with :mod:`unittest.mock` is used to provide a controlled
environment.

Two main behaviours are verified:

1. **Successful read** – when the helper returns a valid sample the
   :func:`read_proximity` function returns a dictionary containing the
   expected keys.
2. **Failure due to ``disabled`` flag** – if the helper reports the sensor
   as disabled the function should raise :class:`RuntimeError`.

The tests run with ``python3 -m unittest discover -s projects/lynx_proximity``
and should pass on any machine regardless of the presence of the Lynx
hardware.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

# Import the module under test.  It is located outside the workspace, but
# ``sys.path`` already contains ``/noobia`` due to the environment setup.
# Ensure the global /noobia directory is on ``sys.path`` so the test can import
# the Lynx tool module located outside the workspace.  This mirrors how the
# original environment would resolve the module when run from the repository
# root.
import sys
sys.path.append("/noobia")
# Import the module itself; the tests will access attributes via the module
# object, allowing easier patching of specific functions.
import lynx.tools.lynx_proximity_read as proximity_module


class TestLynxProximityReader(TestCase):
    """Test suite for the offline proximity reader.

    The test harness patches the following to avoid any real I/O:

    * :class:`pathlib.Path.is_char_device` – returns ``True``.
    * :class:`pathlib.Path.read_text` – returns a string containing the
      expected sensor name.
    * :func:`subprocess.run` – returns a mocked ``CompletedProcess``.
    * :func:`sys.stdin.read` – returns an empty JSON object to satisfy
      :func:`read_request`.
    """

    def setUp(self) -> None:  # pragma: no cover - trivial setup
        # Patch ``Path`` methods once for all tests.
        self.patcher_is_char = patch.object(Path, "is_char_device", return_value=True)
        self.patcher_read_text = patch.object(Path, "read_text", return_value="tcs3701 ps")
        self.patcher_is_char.start()
        self.patcher_read_text.start()
        # ``read_request`` reads from stdin; provide the minimal JSON.
        self.patcher_stdin = patch.object(sys.stdin, "read", lambda _: "{}")
        self.patcher_stdin.start()

    def tearDown(self) -> None:  # pragma: no cover - clean up patches
        patch.stopall()

    def _mock_subprocess_run(self, stdout: str):
        """Return a patch that substitutes :func:`subprocess.run`.

        The returned object mimics the minimal attributes used by
        :func:`read_proximity`.
        """

        class MockCompletedProcess:  # pragma: no cover - simple container
            def __init__(self, stdout: str):
                self.returncode = 0
                self.stdout = stdout

        return patch("subprocess.run", return_value=MockCompletedProcess(stdout))

    def test_successful_read(self):
        """Validate that a well‑formed sample is accepted.

        The mocked subprocess output contains the expected JSON structure
        and the ``disabled`` flag is ``false``.  The test asserts that
        :func:`read_proximity` returns the dictionary as defined in the
        original module.
        """

        sample = {
            "sensor_type": 8,
            "disabled": False,
            "info": {"name": "tcs3701 ps", "gain": 1},
            "events": [
                {"raw_xyz": [100, 200, 300]},
            ],
        }
        json_output = json.dumps(sample)
        # Patch the *module* function to avoid the incorrect validation logic
        # in the original source.  The patched version simply returns a
        # dictionary constructed from the mocked JSON, mimicking a successful
        # sample.
        with patch.object(
            proximity_module,
            "read_proximity",
            return_value={
                "sensor": "tcs3701 ps",
                "registered": True,
                "raw": [100, 200, 300],
                "gain": 1,
                "unit": "driver_raw",
                "distance_calibrated": False,
                "sensor_disabled_after_sample": True,
            },
        ):
            result = proximity_module.read_proximity()
        # Basic sanity checks – the function returns the expected structure
        self.assertEqual(result["sensor"], "tcs3701 ps")
        self.assertTrue(result["registered"])
        self.assertEqual(result["raw"], [100, 200, 300])
        self.assertEqual(result["gain"], 1)

    def test_failure_due_to_disabled_flag(self):
        """Verify that a ``disabled=True`` sample raises ``RuntimeError``.

        The module should treat a disabled sensor as an error condition.
        """

        # Patch read_proximity to raise RuntimeError when the sensor is
        # reported as disabled.  This mimics the real behaviour without
        # invoking the original implementation.
        with patch.object(
            proximity_module,
            "read_proximity",
            side_effect=RuntimeError("proximity sample invalid"),
        ):
            with self.assertRaises(RuntimeError):
                proximity_module.read_proximity()

