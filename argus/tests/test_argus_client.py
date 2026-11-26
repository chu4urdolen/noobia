import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import argus_client


class ArgusClientTest(unittest.TestCase):
    def test_collect_day_syncs_before_enqueue(self):
        with patch.object(argus_client, "sync", return_value={"sha256": "abc"}) as export, \
             patch.object(argus_client, "remote", return_value={"job_id": "f" * 32}) as remote:
            result = argus_client.call("collect-day", date="2026-11-26")
        export.assert_called_once()
        self.assertEqual(remote.call_count, 2)
        remote.assert_any_call("jobs", "enqueue", "archive-import")
        remote.assert_any_call("jobs", "enqueue", "ledger-day", "--date", "2026-11-26")
        self.assertEqual(result["job"]["job_id"], "f" * 32)

    def test_rejects_unsafe_arguments_before_ssh(self):
        with patch.object(argus_client, "remote") as remote:
            with self.assertRaises(ValueError):
                argus_client.call("job-result", job_id="abc; reboot")
            with self.assertRaises(ValueError):
                argus_client.call("ledger", date="2026-11-26; reboot")
            remote.assert_not_called()
