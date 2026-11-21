"""Unit tests for Lynx dynamic brain configuration (task G3)."""

import json
from pathlib import Path
import tempfile
import unittest

from brain_config import BrainConfig, BrainConfigError


class TestBrainConfig(unittest.TestCase):
    def test_default_config_loading(self):
        bc = BrainConfig()
        backends = bc.backends
        self.assertGreaterEqual(len(backends), 2)
        tiers = [b["tier"] for b in backends]
        self.assertEqual(tiers[0], "nexus")
        self.assertEqual(tiers[-1], "cloud")

    def test_select_nexus_when_healthy(self):
        bc = BrainConfig()
        url, model, key = bc.select_backend(
            health_checker=lambda url, timeout_s=2.0: True,
            key_reader=lambda path: "test-nexus-key",
        )
        self.assertIn("192.168.100.106", url)
        self.assertEqual(model, "qwen3.8:27b")
        self.assertEqual(key, "test-nexus-key")

    def test_select_cloud_when_nexus_unhealthy(self):
        bc = BrainConfig()
        url, model, key = bc.select_backend(
            health_checker=lambda url, timeout_s=2.0: False,
            key_reader=lambda path: "test-cloud-key",
        )
        self.assertIn("api.openai.com", url)
        self.assertEqual(model, "gpt-5.4-mini")
        self.assertEqual(key, "test-cloud-key")

    def test_config_reloading_on_change(self):
        with tempfile.NamedTemporaryFile("w+", encoding="utf-8", delete=False) as tf:
            cfg1 = {
                "version": 1,
                "backends": [
                    {"name": "b1", "tier": "nexus", "base_url": "http://b1", "model": "m1", "key_path": "/tmp/k1"}
                ],
            }
            json.dump(cfg1, tf)
            tf.flush()
            cfg_path = tf.name

        try:
            bc = BrainConfig(config_path=cfg_path)
            self.assertEqual(bc.backends[0]["model"], "m1")

            with open(cfg_path, "w", encoding="utf-8") as f:
                cfg2 = {
                    "version": 1,
                    "backends": [
                        {"name": "b2", "tier": "nexus", "base_url": "http://b2", "model": "m2", "key_path": "/tmp/k2"}
                    ],
                }
                json.dump(cfg2, f)

            bc._last_mtime = 0.0  # Force reload
            self.assertEqual(bc.backends[0]["model"], "m2")
        finally:
            Path(cfg_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
