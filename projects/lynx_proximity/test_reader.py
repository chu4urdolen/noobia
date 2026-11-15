"""Unit tests for the Lynx proximity reader.

The tests run in an isolated environment and mock the only external
dependencies of :func:`lynx.tools.lynx_proximity_read.read_proximity`:

* :class:`pathlib.Path.is_char_device`
* :class:`pathlib.Path.read_text`
* :func:`subprocess.run`

Two scenarios are exercised:

1. A *valid* sample where ``disabled`` is ``True`` – the function should
   return a dictionary containing the raw sensor values and the flag
   ``sensor_disabled_after_sample`` set to ``True``.
2. An *invalid* sample where ``disabled`` is ``False`` – the function must
   raise :class:`RuntimeError`.

The test imports the real module from the repository root to avoid
re‑implementing logic.  No hardware is accessed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch, Mock

# Ensure the repository root is on ``sys.path`` so the module can be
# imported by its canonical name.
sys.path.append("/noobia")
import lynx.tools.lynx_proximity_read as proximity_module


class TestLynxProximityReader(TestCase):
    """Test :func:`read_proximity` with mocked dependencies."""

    def setUp(self) -> None:  # pragma: no cover - trivial
        # Patch ``Path`` methods that the real function uses.
        self.patcher_is_char = patch.object(Path, "is_char_device", return_value=True)
        self.patcher_read_text = patch.object(Path, "read_text", return_value="tcs3701 ps")
        self.patcher_is_char.start()
        self.patcher_read_text.start()

    def tearDown(self) -> None:  # pragma: no cover - clean up patches
        patch.stopall()

    def _mock_run(self, stdout: str):
        """Return a patch for :func:`subprocess.run`.

        The patched function yields a simple object with ``returncode`` and
        ``stdout`` attributes, matching the minimal interface used by the
        module.
        """

        class _Completed:
            def __init__(self, stdout: str):
                self.returncode = 0
                self.stdout = stdout

        return patch("subprocess.run", return_value=_Completed(stdout))

    def test_successful_read(self):
        """When the helper reports ``disabled: true`` the sample is valid."""

        sample = {
            "sensor_type": 8,
            "disabled": True,
            "info": {"name": "tcs3701 ps", "gain": 1},
            "events": [{"raw_xyz": [100, 200, 300]}],
        }
        with self._mock_run(json.dumps(sample)):
            result = proximity_module.read_proximity()
        self.assertEqual(result["raw"], [100, 200, 300])
        self.assertTrue(result["sensor_disabled_after_sample"])

    def test_failure_due_to_enabled_flag(self):
        """When ``disabled: false`` the reader should raise an error."""

        sample = {
            "sensor_type": 8,
            "disabled": False,
            "info": {"name": "tcs3701 ps", "gain": 1},
            "events": [{"raw_xyz": [1, 2, 3]}],
        }
        with self._mock_run(json.dumps(sample)):
            with self.assertRaises(RuntimeError):
                proximity_module.read_proximity()

