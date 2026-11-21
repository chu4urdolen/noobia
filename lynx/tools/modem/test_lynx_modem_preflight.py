#!/usr/bin/env python3
"""Unit tests for Lynx Modem (CCCI) Preflight Gate Tool."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from lynx_modem_preflight import (
    CRITICAL_CCCI_DEV_NODES,
    EXPECTED_MD1IMG_SHA256,
    PINNED_BOOT_ID,
    STOCK_MDINIT_SHA256,
    check_stock_artifacts,
    evaluate_fixture,
    evaluate_preflight,
    main,
    sha256_file,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class TestLynxModemPreflight(unittest.TestCase):
    def setUp(self):
        self.valid_status = {
            "boot_id": PINNED_BOOT_ID,
            "battery": {"capacity_percent": 85},
            "thermal": {"max_mC": 31000},
        }
        self.valid_ccci_boot = "md1:0 | md2:n/a | md3:n/a | md4:n/a | md5:n/a"
        self.valid_dev_nodes = list(CRITICAL_CCCI_DEV_NODES) + ["/dev/ccci_0_200"]
        self.stock_details = {
            "ccci_mdinit_sha256": STOCK_MDINIT_SHA256,
            "md1img_sha256": EXPECTED_MD1IMG_SHA256,
            "md1img_size": 80928768,
        }

    def test_sha256_file_valid(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test modem payload")
            f.flush()
            temp_path = f.name
        try:
            h = sha256_file(temp_path)
            self.assertIsNotNone(h)
            self.assertEqual(len(h), 64)
        finally:
            os.remove(temp_path)

    def test_sha256_file_missing(self):
        self.assertIsNone(sha256_file("/nonexistent/path/file.bin"))

    def test_check_stock_artifacts_success(self):
        ok, blockers, details = check_stock_artifacts()
        self.assertTrue(ok, f"Stock artifacts check failed with blockers: {blockers}")
        self.assertEqual(len(blockers), 0)
        self.assertEqual(details["ccci_mdinit_sha256"], STOCK_MDINIT_SHA256)
        self.assertEqual(details["md1img_sha256"], EXPECTED_MD1IMG_SHA256)

    def test_check_stock_artifacts_missing_mdinit(self):
        ok, blockers, _ = check_stock_artifacts(mdinit_path="/nonexistent/ccci_mdinit")
        self.assertFalse(ok)
        self.assertTrue(any("missing" in b for b in blockers))

    def test_check_stock_artifacts_hash_mismatch(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"corrupted binary")
            f.flush()
            temp_path = f.name
        try:
            ok, blockers, _ = check_stock_artifacts(mdinit_path=temp_path)
            self.assertFalse(ok)
            self.assertTrue(any("mismatch" in b for b in blockers))
        finally:
            os.remove(temp_path)

    def test_check_stock_artifacts_missing_partitions(self):
        ok, blockers, _ = check_stock_artifacts(partitions_path="/nonexistent/partitions.json")
        self.assertFalse(ok)
        self.assertTrue(any("manifest missing" in b for b in blockers))

    def test_evaluate_preflight_all_ready(self):
        res = evaluate_preflight(
            status_data=self.valid_status,
            ccci_boot_str=self.valid_ccci_boot,
            present_dev_nodes=self.valid_dev_nodes,
            sim_nodes_unbound=True,
            stock_ok=True,
            stock_blockers=[],
            stock_details=self.stock_details,
        )
        self.assertEqual(res["state"], "ready")
        self.assertEqual(len(res["blockers"]), 0)

    def test_evaluate_preflight_boot_id_mismatch(self):
        bad_status = dict(self.valid_status, boot_id="wrong-boot-id-uuid")
        res = evaluate_preflight(
            status_data=bad_status,
            ccci_boot_str=self.valid_ccci_boot,
            present_dev_nodes=self.valid_dev_nodes,
            sim_nodes_unbound=True,
            stock_ok=True,
            stock_blockers=[],
            stock_details=self.stock_details,
        )
        self.assertEqual(res["state"], "blocked")
        self.assertTrue(any("Boot ID mismatch" in b for b in res["blockers"]))

    def test_evaluate_preflight_battery_too_low(self):
        bad_status = dict(self.valid_status, battery={"capacity_percent": 30})
        res = evaluate_preflight(
            status_data=bad_status,
            ccci_boot_str=self.valid_ccci_boot,
            present_dev_nodes=self.valid_dev_nodes,
            sim_nodes_unbound=True,
            stock_ok=True,
            stock_blockers=[],
            stock_details=self.stock_details,
        )
        self.assertEqual(res["state"], "blocked")
        self.assertTrue(any("Battery too low" in b for b in res["blockers"]))

    def test_evaluate_preflight_thermal_too_high(self):
        bad_status = dict(self.valid_status, thermal={"max_mC": 52000})
        res = evaluate_preflight(
            status_data=bad_status,
            ccci_boot_str=self.valid_ccci_boot,
            present_dev_nodes=self.valid_dev_nodes,
            sim_nodes_unbound=True,
            stock_ok=True,
            stock_blockers=[],
            stock_details=self.stock_details,
        )
        self.assertEqual(res["state"], "blocked")
        self.assertTrue(any("thermal too high" in b for b in res["blockers"]))

    def test_evaluate_preflight_sim_bound(self):
        res = evaluate_preflight(
            status_data=self.valid_status,
            ccci_boot_str=self.valid_ccci_boot,
            present_dev_nodes=self.valid_dev_nodes,
            sim_nodes_unbound=False,
            stock_ok=True,
            stock_blockers=[],
            stock_details=self.stock_details,
        )
        self.assertEqual(res["state"], "blocked")
        self.assertTrue(any("SIM must be out/unbound" in b for b in res["blockers"]))

    def test_evaluate_preflight_missing_dev_nodes(self):
        res = evaluate_preflight(
            status_data=self.valid_status,
            ccci_boot_str=self.valid_ccci_boot,
            present_dev_nodes=["/dev/ccci_ioctl0"],
            sim_nodes_unbound=True,
            stock_ok=True,
            stock_blockers=[],
            stock_details=self.stock_details,
        )
        self.assertEqual(res["state"], "blocked")
        self.assertTrue(any("Missing critical CCCI device nodes" in b for b in res["blockers"]))

    def test_evaluate_preflight_ccci_not_baseline(self):
        res = evaluate_preflight(
            status_data=self.valid_status,
            ccci_boot_str="md1:1 | md2:n/a",
            present_dev_nodes=self.valid_dev_nodes,
            sim_nodes_unbound=True,
            stock_ok=True,
            stock_blockers=[],
            stock_details=self.stock_details,
        )
        self.assertEqual(res["state"], "blocked")
        self.assertTrue(any("not in baseline state md1:0" in b for b in res["blockers"]))

    def test_fixtures_evaluation(self):
        # Ready fixture
        data_ready = json.loads((FIXTURES_DIR / "modem-ready-status.json").read_text())
        res_ready = evaluate_fixture(data_ready)
        self.assertEqual(res_ready["state"], "ready")

        # SIM inserted fixture
        data_sim = json.loads((FIXTURES_DIR / "modem-sim-inserted-blocked.json").read_text())
        res_sim = evaluate_fixture(data_sim)
        self.assertEqual(res_sim["state"], "blocked")
        self.assertTrue(any("SIM must be out/unbound" in b for b in res_sim["blockers"]))

        # Non-baseline md1:1 fixture
        data_md1 = json.loads((FIXTURES_DIR / "modem-md1-booting.json").read_text())
        res_md1 = evaluate_fixture(data_md1)
        self.assertEqual(res_md1["state"], "blocked")
        self.assertTrue(any("not in baseline state md1:0" in b for b in res_md1["blockers"]))


if __name__ == "__main__":
    unittest.main()
