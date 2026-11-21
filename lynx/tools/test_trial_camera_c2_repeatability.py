"""Offline unit tests for Lynx Camera C2 Repeatability Trial."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from trial_camera_c2_repeatability import (
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

    def test_get_yuv_b_irq_count(self):
        def fake_ssh(cmd):
            return 0, "123: 10 20 30 40 50 60 70 80\n", ""

        total = get_yuv_b_irq_count(fake_ssh)
        self.assertEqual(total, 360)

    def test_read_lynx_health(self):
        def fake_ssh(cmd):
            return 0, '{"battery": {"capacity_pct": 80}, "thermal": {"shell_max_c": 35}}', ""

        health = read_lynx_health(fake_ssh)
        self.assertEqual(health["battery"]["capacity_pct"], 80)

    def test_run_c2_trial_success(self):
        irq_counter = [100]

        def fake_ssh(cmd):
            if "interrupts" in cmd:
                irq_counter[0] += 5
                return 0, f"123: {irq_counter[0]}\n", ""
            if "lynx-status" in cmd:
                return 0, '{"battery": {"capacity_pct": 75}, "thermal": {"shell_max_c": 36}}', ""
            return 0, "", ""

        def fake_camsv(idx):
            return True, 1600 * 1200, "captured"

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
        self.assertTrue((self.tmp_dir / "result.json").is_file())

    def test_run_c2_trial_aborts_on_failure(self):
        def fake_ssh(cmd):
            return 0, "123: 100\n", ""

        def fake_camsv(idx):
            if idx == 2:
                return False, 0, "timeout"
            return True, 1600 * 1200, "captured"

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
