#!/usr/bin/env python3
"""repo-secret-scan on a throwaway git repository."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import repo_secret_scan as s  # noqa: E402


class ScanTest(unittest.TestCase):
    def test_finds_keys_terms_and_skips_fixtures(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            (repo / "a.py").write_text('api_key = "q8Zk3mPw9TfLx2Vb"\nfine = 1\n')
            (repo / "b.txt").write_text("-----BEGIN OPENSSH PRIVATE KEY-----\n")
            (repo / "c.sh").write_text("cd /home/alice/work\n")
            (repo / "test_d.py").write_text('token = "q8Zk3mPw9TfLx2Vb"\n')
            (repo / "e.py").write_text('password = "example-password"\n')
            (repo / "untracked.txt").write_text("sk-proj-" + "A" * 30)
            subprocess.run(["git", "-C", str(repo), "add", "a.py", "b.txt", "c.sh", "test_d.py", "e.py"], check=True)
            hits = s.scan(repo, ["Alice"])
            got = sorted((h["file"], h["kind"]) for h in hits)
            self.assertEqual(got, [("a.py", "assigned-secret"), ("b.txt", "private-key"), ("c.sh", "private-term")])
            self.assertNotIn("q8Zk3mPw9TfLx2Vb", str(hits), "values are masked")


if __name__ == "__main__":
    unittest.main()
