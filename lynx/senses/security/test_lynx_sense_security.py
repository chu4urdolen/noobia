"""Unit tests for S10 security sense (LNX-66, LNX-95-99, LNX-74)."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent          # lynx/senses/security
SENSES_DIR = HERE.parent                        # lynx/senses
REPO = HERE.parents[2]                          # /noobia
AUTONOMY_DIR = REPO / "common" / "autonomy"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


lib = _load("lynx_senses_lib", SENSES_DIR / "common" / "lynx_senses_lib.py")
security = _load("lynx_sense_security", HERE / "lynx_sense_security.py")


def _real_sense_module():
    spec = importlib.util.spec_from_file_location("noobia_sense_real", AUTONOMY_DIR / "sense.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RecordingSense:
    def __init__(self, real):
        self._real = real
        self.emits = []

    def format_line(self, *a, **k):
        return self._real.format_line(*a, **k)

    def emit(self, *a, **k):
        self.emits.append((a, k))
        return self._real.format_line(*a, **k)


class SecuritySenseTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="lynx-security-test-")
        self.tmp_dir = Path(self._tmp.name)
        self.state_dir = self.tmp_dir / "state"
        self.state_dir.mkdir(parents=True)
        self.journal_file = str(self.tmp_dir / "security.jsonl")
        self.log_file = str(self.tmp_dir / "dropbear.log")

        self._saved_autonomy_dir = os.environ.get("NOOBIA_AUTONOMY_DIR")
        os.environ["NOOBIA_AUTONOMY_DIR"] = str(AUTONOMY_DIR)
        os.environ["NOOBIA_SENSES_STATE_DIR"] = str(self.state_dir)
        self.recorder = RecordingSense(_real_sense_module())
        security.import_sense = lambda: self.recorder

    def tearDown(self):
        self._tmp.cleanup()
        if self._saved_autonomy_dir is not None:
            os.environ["NOOBIA_AUTONOMY_DIR"] = self._saved_autonomy_dir

    def test_baseline_run_clean(self):
        """On first baseline sample with expected listeners, no alert lines are emitted."""
        expected_sockets = [
            {"proto": "tcp", "ip": "192.168.100.107", "port": 2222, "inode": "1001"},
            {"proto": "tcp", "ip": "192.168.100.107", "port": 22, "inode": "1002"},
            {"proto": "tcp", "ip": "192.168.100.107", "port": 4243, "inode": "1003"},
        ]
        rates = {"wlan0": {"rx_packets": 100, "rx_bytes": 10000}}
        hashes = {"/etc/passwd": "abc123hash"}

        res, code = security.run(
            now=1000,
            journal_file=self.journal_file,
            dropbear_logs=[self.log_file],
            socket_reader=lambda: expected_sockets,
            rate_reader=lambda: rates,
            auth_reader=lambda l, o: ([], o),
            hash_reader=lambda: hashes,
        )
        self.assertEqual(code, 0)
        self.assertEqual(res["emitted_count"], 0)
        self.assertEqual(len(self.recorder.emits), 0)

    def test_unexpected_listener_detected(self):
        """Detects unauthorized listening port (LNX-98: intrusion.suspected)."""
        unexpected_sockets = [
            {"proto": "tcp", "ip": "192.168.100.107", "port": 2222, "inode": "1001"},
            {"proto": "tcp", "ip": "0.0.0.0", "port": 8888, "inode": "2002"},  # Rogue listener!
        ]
        res, code = security.run(
            now=1001,
            journal_file=self.journal_file,
            dropbear_logs=[self.log_file],
            socket_reader=lambda: unexpected_sockets,
            rate_reader=lambda: {},
            auth_reader=lambda l, o: ([], o),
            hash_reader=lambda: {},
        )
        self.assertEqual(code, 0)
        self.assertEqual(res["emitted_count"], 1)
        self.assertEqual(self.recorder.emits[0][0][1], "security")
        self.assertEqual(self.recorder.emits[0][0][2], "intrusion.suspected")
        self.assertEqual(int(self.recorder.emits[0][1]["fields"]["port"]), 8888)

        # Verify incident journal record (LNX-74)
        journal_records = [json.loads(line) for line in Path(self.journal_file).read_text().splitlines()]
        self.assertEqual(len(journal_records), 1)
        self.assertEqual(journal_records[0]["event"], "security.intrusion.suspected")

    def test_auth_failure_perception(self):
        """Detects dropbear authentication failures (LNX-96: authentication.failed)."""
        auth_fails = [
            {"service": "ssh", "ip": "192.168.100.55", "port": 49120, "user": "admin", "line": "fail 1"},
            {"service": "ssh", "ip": "192.168.100.55", "port": 49122, "user": "admin", "line": "fail 2"},
        ]
        res, code = security.run(
            now=1002,
            journal_file=self.journal_file,
            dropbear_logs=[self.log_file],
            socket_reader=lambda: [],
            rate_reader=lambda: {},
            auth_reader=lambda l, o: (auth_fails, o),
            hash_reader=lambda: {},
        )
        self.assertEqual(code, 0)
        self.assertEqual(res["emitted_count"], 1)
        self.assertEqual(self.recorder.emits[0][0][2], "authentication.failed")
        self.assertEqual(self.recorder.emits[0][1]["fields"]["source_ip"], "192.168.100.55")
        self.assertEqual(int(self.recorder.emits[0][1]["fields"]["attempts"]), 2)

    def test_network_flood_detected(self):
        """Detects packet surge exceeding threshold (LNX-97: flood.detected)."""
        # Sample 1: Baseline
        security.run(
            now=1000,
            journal_file=self.journal_file,
            dropbear_logs=[self.log_file],
            socket_reader=lambda: [],
            rate_reader=lambda: {"wlan0": {"rx_packets": 100, "rx_bytes": 1000}},
            auth_reader=lambda l, o: ([], o),
            hash_reader=lambda: {},
        )
        # Sample 2: Surge of 2000 pps over 1s (threshold is 1500)
        res, code = security.run(
            now=1001,
            journal_file=self.journal_file,
            dropbear_logs=[self.log_file],
            socket_reader=lambda: [],
            rate_reader=lambda: {"wlan0": {"rx_packets": 2100, "rx_bytes": 2000000}},
            auth_reader=lambda l, o: ([], o),
            hash_reader=lambda: {},
        )
        self.assertEqual(code, 0)
        self.assertEqual(res["emitted_count"], 1)
        self.assertEqual(self.recorder.emits[0][0][2], "flood.detected")
        self.assertEqual(self.recorder.emits[0][1]["fields"]["iface"], "wlan0")
        self.assertEqual(int(self.recorder.emits[0][1]["fields"]["pps"]), 2000)

    def test_integrity_changed_detected(self):
        """Detects modification of critical configuration file (LNX-99: integrity.changed)."""
        # Baseline
        security.run(
            now=1000,
            journal_file=self.journal_file,
            dropbear_logs=[self.log_file],
            socket_reader=lambda: [],
            rate_reader=lambda: {},
            auth_reader=lambda l, o: ([], o),
            hash_reader=lambda: {"/etc/passwd": "original_hash"},
        )
        # File modified
        res, code = security.run(
            now=1002,
            journal_file=self.journal_file,
            dropbear_logs=[self.log_file],
            socket_reader=lambda: [],
            rate_reader=lambda: {},
            auth_reader=lambda l, o: ([], o),
            hash_reader=lambda: {"/etc/passwd": "altered_hash"},
        )
        self.assertEqual(code, 0)
        self.assertEqual(res["emitted_count"], 1)
        self.assertEqual(self.recorder.emits[0][0][2], "integrity.changed")
        self.assertEqual(self.recorder.emits[0][1]["fields"]["path"], "/etc/passwd")


if __name__ == "__main__":
    unittest.main()
