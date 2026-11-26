import sys
from types import SimpleNamespace
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

    def test_remote_query_is_shell_quoted(self):
        completed = SimpleNamespace(returncode=0, stdout="[]", stderr="")
        with patch.object(argus_client.subprocess, "run", return_value=completed) as run:
            self.assertEqual(argus_client.call("find-events", query="Argus; whoami"),
                             {"items": [], "next_offset": None})
        remote_command = run.call_args.args[0][-1]
        self.assertIn("'Argus; whoami'", remote_command)

    def test_page_has_explicit_continuation(self):
        with patch.object(argus_client, "remote", return_value=list(range(101))) as remote:
            result = argus_client.call("events-on", date="2026-11-26", offset=200)
        self.assertEqual(len(result["items"]), 100)
        self.assertEqual(result["next_offset"], 300)
        remote.assert_called_once_with("history", "events-on", "2026-11-26",
                                       "--limit", "101", "--offset", "200")

    def test_source_lookup_requires_exact_hash(self):
        with patch.object(argus_client, "remote") as remote:
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                argus_client.call("source-record", kind="forge", key="note:1", sha256="short")
            remote.assert_not_called()
