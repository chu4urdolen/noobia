"""Receipt checks before relying on Lynx's filesystem growth result."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_alpine_root_growth import EXPECTED, audit


class RootGrowthAuditTest(unittest.TestCase):
    def receipt(self):
        before = dict(EXPECTED, boot_id="new-boot", block_count=262_144,
                      label="LYNXROOT", state="clean", status={"issues": []})
        after = dict(before, block_count=EXPECTED["partition_sectors"] // 8)
        return {"state": "grown-and-verified", "before": before, "after": after}

    def test_valid_growth(self):
        self.assertEqual(audit(self.receipt())["status"], "pass")

    def test_rejects_tampered_identity(self):
        receipt = self.receipt()
        receipt["after"]["uuid"] = "other"
        with self.assertRaisesRegex(ValueError, "uuid"):
            audit(receipt)

    def test_rejects_missing_status_and_undersized_growth(self):
        receipt = self.receipt()
        del receipt["after"]["status"]
        with self.assertRaisesRegex(ValueError, "status"):
            audit(receipt)
        receipt = self.receipt()
        receipt["after"]["block_count"] = 300_000
        with self.assertRaisesRegex(ValueError, "capacity"):
            audit(receipt)

    def test_rejects_stopped_receipt(self):
        receipt = self.receipt()
        receipt["state"] = "stopped"
        with self.assertRaisesRegex(ValueError, "completed growth"):
            audit(receipt)


if __name__ == "__main__":
    unittest.main()
