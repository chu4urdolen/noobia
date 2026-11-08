import json
import os
import pathlib
import tempfile
import unittest

import audit
from audit import run_audit


class TestAudit(unittest.TestCase):
    def _make_result(self, *, state="grown-and-verified", before=None, after=None):
        # Base snapshot values
        before = before or {
            "serial": "PHONE_SERIAL",
            "boot_sha256": "abc123",
            "boot_id": "boot-id-1",
            "start_sector": 1000,
            "partition_sectors": 20000,  # 2500 blocks
            "uuid": "uuid-1",
            "block_size": 4096,
            "block_count": 2000,
            "status": {"issues": False},
        }
        after = after or {
            "serial": before["serial"],
            "boot_sha256": before["boot_sha256"],
            "boot_id": before["boot_id"],
            "start_sector": before["start_sector"],
            "partition_sectors": before["partition_sectors"],
            "uuid": before["uuid"],
            "block_size": before["block_size"],
            "block_count": 2500,  # increased
            "status": {"issues": False},
        }
        data = {"state": state, "before": before, "after": after}
        return data

    def _run_and_assert(self, data, expected_pass):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "result.json"
            p.write_text(json.dumps(data))
            verdict = run_audit(p)
            self.assertEqual(verdict["status"], "pass" if expected_pass else "fail")

    def test_valid(self):
        data = self._make_result()
        self._run_and_assert(data, True)

    def test_tampered_identity(self):
        data = self._make_result()
        data["after"]["serial"] = "BAD_SERIAL"
        self._run_and_assert(data, False)

    def test_undersized_growth(self):
        data = self._make_result()
        # Make post block count just below 95%
        partition_blocks = data["after"]["partition_sectors"] // 8
        data["after"]["block_count"] = partition_blocks * 94 // 100
        self._run_and_assert(data, False)

    def test_stopped_state(self):
        data = self._make_result(state="stopped")
        self._run_and_assert(data, False)

