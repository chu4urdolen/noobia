"""Offline package integrity check for the coordinated MCP catalog update."""

import hashlib
import io
import tarfile
import unittest

import deploy_native_mcp_catalog as deploy


class TestMcpPackage(unittest.TestCase):
    def test_staged_archive_has_exact_verified_sources(self):
        files = deploy.local_files()
        self.assertEqual(len(files), 17)
        with tarfile.open(fileobj=io.BytesIO(deploy.archive_payload(files))) as archive:
            staged = {member.name: archive.extractfile(member).read()
                      for member in archive if member.isfile()}
        self.assertEqual(set(staged), set(files) | {"SHA256SUMS"})
        for name, (source, _target, _mode) in files.items():
            with self.subTest(name=name):
                self.assertEqual(staged[name], source)
                digest = hashlib.sha256(source).hexdigest()
                self.assertIn(f"{digest}  {name}\n".encode(), staged["SHA256SUMS"])


if __name__ == "__main__":
    unittest.main()
