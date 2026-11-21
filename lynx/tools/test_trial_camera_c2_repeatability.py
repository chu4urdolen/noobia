"""Offline unit tests for Lynx Camera C2 Repeatability Trial (E1-E4)."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from trial_camera_c2_repeatability import (
    compute_frame_statistics,
    check_kernel_oops,
    get_yuv_b_irq_count,
    read_lynx_health,
    run_c2_trial,
)


class TestCameraC2Repeatability(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="c2-test-")
        self.tmp_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_compute_frame_statistics_valid_and_flat(self):
        # 1. Valid frame with gradient
        valid_bytes = bytearray(1600 * 1200)
        for i in range(len(valid_bytes)):
            valid_bytes[i] = (i % 256)
        stats = compute_frame_statistics(bytes(valid_bytes))
        self.assertTrue(stats["valid"])
        self.assertEqual(stats["unique_values"], 256)
        self.assertLess(stats["dominant_fraction"], 0.05)

        # 2. Flat all-zero frame (invalid)
        flat_bytes = bytes([0] * (1600 * 1200))
        flat_stats = compute_frame_statistics(flat_bytes)
        self.assertFalse(flat_stats["valid"])
        self.assertEqual(flat_stats["unique_values"], 1)

    def test_get_yuv_b_irq_count(self):
        def fake_ssh(cmd):
            return 0, "123: 10 20 30 40 50 60 70 80\n", ""

        total = get_yuv_b_irq_count(fake_ssh)
        self.assertEqual(total, 360)

    def test_check_kernel_oops(self):
        def fake_ssh_clean(cmd):
            return 0, "0\n", ""

        def fake_ssh_oops(cmd):
            return 0, "2\n", ""

        has_oops, count = check_kernel_oops(fake_ssh_clean)
        self.assertFalse(has_oops)
        self.assertEqual(count, 0)

        has_oops, count = check_kernel_oops(fake_ssh_oops)
        self.assertTrue(has_oops)
        self.assertEqual(count, 2)

    def test_read_lynx_health_keys(self):
        def fake_ssh(cmd):
            return 0, '{"battery": {"capacity_percent": 82}, "thermal": {"max_mC": 36500}}', ""

        health = read_lynx_health(fake_ssh)
        self.assertEqual(health["battery_percent"], 82)
        self.assertEqual(health["temp_c"], 36.5)

    def test_run_c2_trial_success(self):
        irq_counter = [100]

        def fake_ssh(cmd):
            if "interrupts" in cmd:
                irq_counter[0] += 5
                return 0, f"123: {irq_counter[0]}\n", ""
            if "lynx-status" in cmd:
                return 0, '{"battery": {"capacity_percent": 75}, "thermal": {"max_mC": 36000}}', ""
            if "Oops" in cmd:
                return 0, "0\n", ""
            return 0, "", ""

        def fake_camsv(idx):
            stats = {"valid": True, "unique_values": 100, "dominant_fraction": 0.1}
            return True, 1600 * 1200, "captured", stats

        rep = run_c2_trial(
            boot_id="test-boot-123",
            iterations=3,
            settle_s=0.0,
            attended=True,
            output_dir=self.tmp_dir,
            ssh_fn=fake_ssh,
            camsv_cmd_fn=fake_camsv,
        )

        self.assertEqual(rep["state"], "c2_repeatability_passed")
        self.assertEqual(rep["successful_iterations"], 3)
        self.assertEqual(rep["initial_health"]["battery_percent"], 75)
        self.assertEqual(rep["initial_health"]["temp_c"], 36.0)
        self.assertTrue((self.tmp_dir / "result.json").is_file())

    def test_run_c2_trial_aborts_on_oops(self):
        oops_active = [False]

        def fake_ssh(cmd):
            if "interrupts" in cmd:
                return 0, "123: 105\n", ""
            if "lynx-status" in cmd:
                return 0, '{"battery": {"capacity_percent": 75}, "thermal": {"max_mC": 36000}}', ""
            if "Oops" in cmd:
                return 0, "1\n" if oops_active[0] else "0\n", ""
            return 0, "", ""

        def fake_camsv(idx):
            if idx == 2:
                oops_active[0] = True
            stats = {"valid": True, "unique_values": 100, "dominant_fraction": 0.1}
            return True, 1600 * 1200, "captured", stats

        rep = run_c2_trial(
            boot_id="test-boot-123",
            iterations=3,
            settle_s=0.0,
            attended=True,
            output_dir=self.tmp_dir,
            ssh_fn=fake_ssh,
            camsv_cmd_fn=fake_camsv,
        )

        self.assertEqual(rep["state"], "aborted_oops_at_iteration_2")
        self.assertEqual(rep["successful_iterations"], 1)

    def test_run_c2_trial_aborts_on_failure(self):
        def fake_ssh(cmd):
            if "lynx-status" in cmd:
                return 0, '{"battery": {"capacity_percent": 75}, "thermal": {"max_mC": 36000}}', ""
            return 0, "123: 100\n", ""

        def fake_camsv(idx):
            if idx == 2:
                return False, 0, "timeout", None
            stats = {"valid": True, "unique_values": 100, "dominant_fraction": 0.1}
            return True, 1600 * 1200, "captured", stats

        rep = run_c2_trial(
            boot_id="test-boot-123",
            iterations=3,
            settle_s=0.0,
            attended=True,
            output_dir=self.tmp_dir,
            ssh_fn=fake_ssh,
            camsv_cmd_fn=fake_camsv,
        )

        self.assertEqual(rep["state"], "aborted_at_iteration_2")
        self.assertEqual(rep["successful_iterations"], 1)


if __name__ == "__main__":
    unittest.main()
