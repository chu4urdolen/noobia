"""Unit tests for Lynx autonomous cellular & 5G diagnostic toolkit."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from lynx.tools.cellular_diag import lynx_cellular_diag as cell


class TestCellularDiag(unittest.TestCase):
    def test_5g_bands_Nord3(self):
        res = cell.bands_5g()
        self.assertTrue(res["ok"])
        self.assertEqual(res["nr_bands_count"], 13)
        self.assertIn("n78", res["nr_bands"])
        self.assertIn("n1", res["nr_bands"])
        self.assertEqual(res["lte_bands_count"], 21)
        self.assertIn("5G radio capability audit", res["sentence"])

    @patch("lynx.tools.cellular_diag.lynx_cellular_diag.glob.glob")
    @patch("os.path.exists")
    def test_sim_check(self, mock_exists, mock_glob):
        mock_glob.return_value = [
            "/sys/devices/platform/MD1_SIM1_HOT_PLUG_EINT",
            "/sys/devices/platform/MD1_SIM2_HOT_PLUG_EINT",
        ]
        mock_exists.return_value = True
        res = cell.sim_check()
        self.assertTrue(res["ok"])
        self.assertFalse(res["card_present"])
        self.assertEqual(res["hotplug_nodes"], 2)
        self.assertIn("Dual-SIM tray hardware detected", res["sentence"])

    @patch("lynx.tools.cellular_diag.lynx_cellular_diag.glob.glob")
    @patch("lynx.tools.cellular_diag.lynx_cellular_diag.run_cmd")
    def test_modem_status(self, mock_cmd, mock_glob):
        mock_glob.return_value = ["/dev/ccci_ioctl0", "/dev/ttyC0", "/dev/ccci_md1_sta"]
        mock_cmd.return_value = (0, "ccci_md_all 561152 4\nccmni 40960 1", "")
        with patch.object(Path, "read_text", return_value="md1:0"):
            with patch("os.path.exists", return_value=True):
                res = cell.modem_status()
                self.assertTrue(res["ok"])
                self.assertEqual(res["ccci_nodes_count"], 3)
                self.assertIn("Cellular modem status", res["sentence"])

    def test_action_lock_concurrency(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("lynx.tools.cellular_diag.lynx_cellular_diag.LOCK_DIR", Path(tmpdir)):
                lock1 = cell.ActionLock("test_cell")
                lock2 = cell.ActionLock("test_cell")
                self.assertTrue(lock1.acquire())
                self.assertFalse(lock2.acquire())
                lock1.release()
                self.assertTrue(lock2.acquire())
                lock2.release()


if __name__ == "__main__":
    unittest.main()
