"""Unit tests for compute routing (task E5)."""

import json
from pathlib import Path
import tempfile
import unittest

from route import Router, Backend, RoutingError


class TestRoute(unittest.TestCase):
    def test_nexus_first_priority(self):
        b_nexus = Backend(name="nexus-1", tier="nexus", endpoint="http://192.168.100.106:11434", health_check=lambda: True)
        b_local = Backend(name="local-1", tier="local", endpoint="http://127.0.0.1:11434", health_check=lambda: True)
        b_cloud = Backend(name="cloud-1", tier="cloud", endpoint="https://api.openai.com/v1", health_check=lambda: True)

        r = Router(custom_backends={"inference": [b_nexus, b_local, b_cloud]})
        selected = r.route("inference")
        self.assertEqual(selected.tier, "nexus")
        self.assertEqual(selected.name, "nexus-1")

    def test_fallback_to_local_when_nexus_unhealthy(self):
        b_nexus = Backend(name="nexus-1", tier="nexus", endpoint="http://nexus", health_check=lambda: False)
        b_local = Backend(name="local-1", tier="local", endpoint="http://local", health_check=lambda: True)
        b_cloud = Backend(name="cloud-1", tier="cloud", endpoint="http://cloud", health_check=lambda: True)

        r = Router(custom_backends={"detect": [b_nexus, b_local, b_cloud]})
        selected = r.route("detect")
        self.assertEqual(selected.tier, "local")
        self.assertEqual(selected.name, "local-1")

    def test_fallback_to_cloud_when_nexus_and_local_unhealthy(self):
        b_nexus = Backend(name="nexus-1", tier="nexus", endpoint="http://nexus", health_check=lambda: False)
        b_local = Backend(name="local-1", tier="local", endpoint="http://local", health_check=lambda: False)
        b_cloud = Backend(name="cloud-1", tier="cloud", endpoint="http://cloud", health_check=lambda: True)

        r = Router(custom_backends={"stt": [b_nexus, b_local, b_cloud]})
        selected = r.route("stt")
        self.assertEqual(selected.tier, "cloud")
        self.assertEqual(selected.name, "cloud-1")

    def test_exhausted_backends_raises_error(self):
        b_nexus = Backend(name="nexus-1", tier="nexus", endpoint="http://nexus", health_check=lambda: False)
        r = Router(custom_backends={"tts": [b_nexus]})
        with self.assertRaises(RoutingError):
            r.route("tts")

    def test_config_reloading_on_mtime_change(self):
        with tempfile.NamedTemporaryFile("w+", encoding="utf-8", delete=False) as tf:
            cfg1 = {"inference": [{"name": "nexus-a", "tier": "nexus", "endpoint": "mock://a"}]}
            json.dump(cfg1, tf)
            tf.flush()
            cfg_path = tf.name

        try:
            r = Router(config_path=cfg_path)
            self.assertEqual(r.route("inference").name, "nexus-a")

            # Update file
            with open(cfg_path, "w", encoding="utf-8") as f:
                cfg2 = {"inference": [{"name": "nexus-b", "tier": "nexus", "endpoint": "mock://b"}]}
                json.dump(cfg2, f)

            r._last_mtime = 0.0  # Force reload trigger
            self.assertEqual(r.route("inference").name, "nexus-b")
        finally:
            Path(cfg_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
