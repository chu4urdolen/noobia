"""Unit tests for the Lynx agent backend selection logic.

The tests patch :func:`lynx_agent.local_available` and :func:`lynx_agent.key_from`
to avoid any real network or file I/O.  The goal is to verify that the
``backend`` function chooses the correct backend URL, model, and key under
different conditions.
"""

import importlib
import unittest
from unittest import mock

# Import the module under test from its absolute path to avoid relying on the
# package being importable via ``lynx``.  The repository root is not on
# ``sys.path`` during tests, so we load the file directly.
module_file = "/noobia/lynx/tools/agent/lynx_agent.py"
spec = importlib.util.spec_from_file_location("lynx_agent", module_file)
lynx_agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lynx_agent)


class TestBackendSelection(unittest.TestCase):
    """Test the ``backend`` function's selection logic."""

    @mock.patch.object(lynx_agent, "local_available", return_value=True)
    @mock.patch.object(lynx_agent, "key_from", side_effect=lambda p: "localkey")
    def test_healthy_nexus_uses_local(self, _mock_key, _mock_local):
        """When the local Nexus health endpoint is reachable, the local backend
        should be selected with the OSS 20b model.
        """
        url, model, key = lynx_agent.backend()
        self.assertEqual(url, lynx_agent.LOCAL)
        self.assertEqual(model, "gpt-oss-20b")
        self.assertEqual(key, "localkey")

    @mock.patch.object(lynx_agent, "local_available", return_value=False)
    @mock.patch.object(lynx_agent, "key_from", side_effect=lambda p: "cloudkey")
    def test_unreachable_nexus_uses_cloud(self, _mock_key, _mock_local):
        """When the local Nexus health endpoint is unreachable, the cloud
        backend should be selected with the OpenAI model.
        """
        url, model, key = lynx_agent.backend()
        self.assertEqual(url, lynx_agent.CLOUD)
        self.assertEqual(model, "gpt-5.4-mini")
        self.assertEqual(key, "cloudkey")

    @mock.patch.object(lynx_agent, "local_available", return_value=True)
    @mock.patch.object(lynx_agent, "key_from", side_effect=lambda p: (_ for _ in ()).throw(RuntimeError("bad key")))
    def test_missing_local_key_errors_without_fallback(self, _mock_key, _mock_local):
        """If the local key is missing or invalid, ``backend`` should raise
        ``RuntimeError`` instead of falling back to the cloud.
        """
        with self.assertRaises(RuntimeError):
            lynx_agent.backend()


if __name__ == "__main__":
    unittest.main()

