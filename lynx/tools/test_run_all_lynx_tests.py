#!/usr/bin/env python3
"""Unit tests for the consolidated Lynx test-suite runner (D20)."""

import json
import tempfile
import unittest
from pathlib import Path

import run_all_lynx_tests as R


def make_tree(base: Path) -> dict:
    """Build a synthetic tools tree: top-level + subdirs + pycache decoy."""
    (base / "agent").mkdir(parents=True)
    (base / "ui").mkdir()
    (base / "__pycache__").mkdir()
    top = base / "test_alpha.py"
    sub = base / "agent" / "test_beta.py"
    sub2 = base / "ui" / "test_gamma.py"
    decoy = base / "__pycache__" / "test_cached.py"
    for f in (top, sub, sub2, decoy):
        f.write_text("import unittest\n")
    return {"top": top, "sub": sub, "sub2": sub2, "decoy": decoy}


class TestDiscovery(unittest.TestCase):
    def test_discovers_top_level_and_subdirs(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            tree = make_tree(base)
            files = R.discover_test_files(base)
            names = sorted(f.name for f in files)
            self.assertEqual(names, ["test_alpha.py", "test_beta.py", "test_gamma.py"])

    def test_empty_tree(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(R.discover_test_files(Path(td)), [])


class TestWhitespaceScanner(unittest.TestCase):
    def _scan(self, name: str, content: bytes):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            f = base / name
            f.write_bytes(content)
            return R.scan_whitespace_file(f, base)

    def test_flags_single_trailing_space(self):
        v = self._scan("tool.py", b"x = 1 \n")
        self.assertEqual(len(v), 1)
        self.assertEqual(v[0].kind, "trailing-whitespace")

    def test_flags_trailing_tab(self):
        v = self._scan("tool.py", b"x = 1\t\n")
        self.assertEqual(len(v), 1)

    def test_exempts_markdown_hard_breaks(self):
        self.assertEqual(self._scan("doc.md", b"line one  \nline two  \n"), [])

    def test_flags_stray_single_space_in_markdown(self):
        v = self._scan("doc.md", b"item: \nother\n")
        self.assertEqual(len(v), 1)

    def test_exempts_patch_files(self):
        self.assertEqual(self._scan("x.patch", b"context line \n+\tadded\n"), [])
        self.assertEqual(self._scan("x.diff", b"a  \nb\n"), [])

    def test_flags_missing_eof_newline(self):
        v = self._scan("tool.py", b"x = 1")
        kinds = [x.kind for x in v]
        self.assertIn("missing-eof-newline", kinds)

    def test_flags_conflict_markers(self):
        v = self._scan("tool.py", b"<<<<<<< ours\nx\n>>>>>>> theirs\n")
        self.assertIn("conflict-marker", [x.kind for x in v])

    def test_skips_binary_files(self):
        self.assertEqual(self._scan("blob.bin", b"\x00\x01trailing \n"), [])


class TestRunSuite(unittest.TestCase):
    def test_passing_suite(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "test_ok.py"
            f.write_text(
                "import unittest\n"
                "class T(unittest.TestCase):\n"
                "    def test_one(self):\n"
                "        self.assertTrue(True)\n"
                "if __name__ == '__main__':\n"
                "    unittest.main()\n"
            )
            r = R.run_suite(f, timeout=60)
            self.assertTrue(r.ok, r.detail)
            self.assertGreaterEqual(r.tests, 1)

    def test_failing_suite(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "test_bad.py"
            f.write_text(
                "import unittest\n"
                "class T(unittest.TestCase):\n"
                "    def test_one(self):\n"
                "        self.fail('deliberate')\n"
            )
            r = R.run_suite(f, timeout=60)
            self.assertFalse(r.ok)


class TestRendering(unittest.TestCase):
    def test_markdown_summary_pass(self):
        results = [
            R.SuiteResult(suite="test_alpha", path="x/test_alpha.py",
                          tests=3, ok=True, duration=0.5),
        ]
        md = R.render_markdown(results, [], wall=1.25)
        self.assertIn("**Overall: PASS**", md)
        self.assertIn("| test_alpha | 3 | OK | 0.50 |", md)
        self.assertIn("Whitespace sanity", md)
        self.assertIn("CLEAN", md)

    def test_markdown_summary_fail_and_violations(self):
        results = [
            R.SuiteResult(suite="test_bad", path="x/test_bad.py",
                          tests=2, ok=False, duration=0.2, detail="1 failure"),
        ]
        ws = [R.WhitespaceViolation("lynx/tools/x.py", 7, "trailing-whitespace")]
        md = R.render_markdown(results, ws, wall=0.9)
        self.assertIn("**Overall: FAIL**", md)
        self.assertIn("1 violation(s)", md)
        self.assertIn("`lynx/tools/x.py`:7 trailing-whitespace", md)

    def test_json_payload_shape(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            (base / "test_json.py").write_text(
                "import unittest\n"
                "class T(unittest.TestCase):\n"
                "    def test_one(self):\n"
                "        self.assertTrue(True)\n"
            )
            f = base / "test_json.py"
            r = R.run_suite(f, timeout=60)
            md = R.render_markdown([r], [], 1.0)
            self.assertIn("PASS", md)


class TestClassification(unittest.TestCase):
    def test_standalone_script_fallback_ok(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "test_script_ok.py"
            f.write_text(
                "#!/usr/bin/env python3\n"
                "print('offline fixtures passed')\n"
            )
            r = R.run_suite(f, timeout=60)
            self.assertTrue(r.ok, r.detail)
            self.assertEqual(r.status, "script-ok")

    def test_standalone_script_fallback_failure(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "test_script_bad.py"
            f.write_text(
                "#!/usr/bin/env python3\n"
                "def main():\n"
                "    raise SystemExit(3)\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            )
            r = R.run_suite(f, timeout=60)
            self.assertFalse(r.ok)
            self.assertEqual(r.status, "script-failed")
            self.assertIn("exit 3", r.detail)

    def test_env_blocked_missing_python_module(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "test_missing_dep.py"
            f.write_text("import totally_missing_module_zzz\n")
            r = R.run_suite(f, timeout=60)
            self.assertFalse(r.ok)
            self.assertEqual(r.status, "env-blocked")
            self.assertIn("totally_missing_module_zzz", r.missing)

    def test_env_blocked_missing_binary(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "test_missing_bin.py"
            f.write_text(
                "import subprocess\n"
                "subprocess.run(['definitely-missing-binary-zzz'])\n"
            )
            r = R.run_suite(f, timeout=60)
            self.assertFalse(r.ok)
            self.assertEqual(r.status, "env-blocked")
            self.assertIn("definitely-missing-binary-zzz", r.missing)

    def test_build_child_env_finds_modinfo_in_sbin(self):
        import os
        import shutil
        if not (Path("/usr/sbin/modinfo")).is_file():
            self.skipTest("modinfo not installed on this host")
        saved = dict(os.environ)
        try:
            os.environ["PATH"] = "/usr/bin:/bin"
            env = R.build_child_env()
            self.assertTrue(shutil.which("modinfo", path=env["PATH"]),
                            env["PATH"])
        finally:
            os.environ.clear()
            os.environ.update(saved)


class TestOverallOk(unittest.TestCase):
    def mk(self, **kw):
        base = {"suite": "s", "path": "p"}
        base.update(kw)
        return R.SuiteResult(**base)

    def test_green(self):
        self.assertTrue(R.overall_ok([self.mk(ok=True, status="ok")], [], False))

    def test_script_ok_counts_green(self):
        self.assertTrue(R.overall_ok([self.mk(ok=True, status="script-ok")], [], False))

    def test_failed_suite(self):
        self.assertFalse(R.overall_ok([self.mk(ok=False, status="failed")], [], False))

    def test_script_failed_suite(self):
        self.assertFalse(R.overall_ok([self.mk(ok=False, status="script-failed")], [], False))

    def test_env_blocked_lenient_default(self):
        r = self.mk(ok=False, status="env-blocked", missing="python:dbus_next")
        self.assertTrue(R.overall_ok([r], [], strict=False))

    def test_env_blocked_strict(self):
        r = self.mk(ok=False, status="env-blocked", missing="python:dbus_next")
        self.assertFalse(R.overall_ok([r], [], strict=True))

    def test_whitespace_gate(self):
        ws = [R.WhitespaceViolation("lynx/tools/x.py", 7, "trailing-whitespace")]
        self.assertFalse(R.overall_ok([self.mk(ok=True, status="ok")], ws, False))

    def test_empty_results(self):
        self.assertFalse(R.overall_ok([], [], False))

    def test_render_reports_env_blocked(self):
        r = self.mk(ok=False, status="env-blocked", missing="python:dbus_next")
        md = R.render_markdown([r], [], 1.0, strict=False)
        self.assertIn("ENV-BLOCKED", md)
        self.assertIn("dbus_next", md)
        self.assertIn("1 env-blocked", md)


class TestArtifactClassification(unittest.TestCase):
    """D29: missing-artifact errors classify as env-blocked; real failures stay failed."""

    def _write(self, td: str, name: str, body: str) -> Path:
        f = Path(td) / name
        f.write_text(body)
        return f

    def test_unittest_suite_not_found_at_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            f = self._write(td, "test_art1.py",
                "import unittest\n"
                "class T(unittest.TestCase):\n"
                "    def test_one(self):\n"
                "        raise RuntimeError('stock mtu3.ko not found at "
                "/x/lynx/linux-port/artifacts/stock/mtu3.ko')\n"
            )
            r = R.run_suite(f, timeout=60)
            self.assertFalse(r.ok)
            self.assertEqual(r.status, "env-blocked", r.detail)
            self.assertIn("missing artifact:", r.missing)
            self.assertIn("artifacts/", r.missing)

    def test_unittest_suite_fileerror_on_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            f = self._write(td, "test_art2.py",
                "import unittest\n"
                "class T(unittest.TestCase):\n"
                "    def test_one(self):\n"
                "        with open('/x/artifacts/busybox/build-validation.json'):\n"
                "            pass\n"
            )
            r = R.run_suite(f, timeout=60)
            self.assertEqual(r.status, "env-blocked", r.detail)
            self.assertIn("missing artifact:", r.missing)

    def test_standalone_script_missing_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            f = self._write(td, "test_art3.py",
                "#!/usr/bin/env python3\n"
                "# uncaught, like the real v47 retry script\n"
                "with open('/x/artifacts/wifi-dhcp-retry/nord3.img'):\n"
                "    pass\n"
            )
            r = R.run_suite(f, timeout=60)
            self.assertEqual(r.status, "env-blocked", r.detail)
            self.assertIn("missing artifact:", r.missing)

    def test_mixed_real_failure_stays_failed(self):
        with tempfile.TemporaryDirectory() as td:
            f = self._write(td, "test_mix.py",
                "import unittest\n"
                "class T(unittest.TestCase):\n"
                "    def test_real_failure(self):\n"
                "        self.fail('deliberate')\n"
                "    def test_artifact(self):\n"
                "        raise RuntimeError('not found at /x/artifacts/y/mtu3.ko')\n"
            )
            r = R.run_suite(f, timeout=60)
            self.assertEqual(r.status, "failed", r.detail)

    def test_non_artifact_fileerror_stays_failed(self):
        with tempfile.TemporaryDirectory() as td:
            f = self._write(td, "test_nonart.py",
                "import unittest\n"
                "class T(unittest.TestCase):\n"
                "    def test_one(self):\n"
                "        with open('/x/data/config.json'):\n"
                "            pass\n"
            )
            r = R.run_suite(f, timeout=60)
            self.assertEqual(r.status, "failed", r.detail)

    def test_env_blocked_detail_labels_artifact(self):
        stderr = ("ERROR: test_x\n"
                  "FileNotFoundError: [Errno 2] No such file or directory: "
                  "'/x/lynx/linux-port/artifacts/a/b.json'\n")
        self.assertEqual(
            R._env_blocked_detail(stderr),
            "missing artifact: /x/lynx/linux-port/artifacts/a/b.json")

    def test_env_blocked_detail_keeps_binary(self):
        stderr = ("FileNotFoundError: [Errno 2] "
                  "No such file or directory: '/usr/bin/xyz'\n")
        self.assertEqual(R._env_blocked_detail(stderr),
                         "missing binary: /usr/bin/xyz")

    def test_failure_blocks_helper_requires_blocks(self):
        self.assertFalse(R._failure_blocks_artifact_only("Ran 0 tests"))
        self.assertTrue(R._failure_blocks_artifact_only(
            "ERROR: test_a\n"
            "RuntimeError: not found at /x/artifacts/stock/mtu3.ko\n"))


class TestLiveLynxTree(unittest.TestCase):
    def test_tracked_lynx_tree_is_whitespace_clean(self):
        """The real gate: every tracked lynx file passes the scan."""
        repo_root = Path(__file__).resolve().parent.parent.parent
        if not (repo_root / ".git").exists():
            self.skipTest("not in the noobia repository")
        ws = []
        for tf in R.tracked_files(repo_root, "lynx"):
            ws.extend(R.scan_whitespace_file(tf, repo_root))
        self.assertEqual(
            ws, [],
            "trailing-whitespace/convention violations: "
            + ", ".join(f"{v.path}:{v.line} {v.kind}" for v in ws[:10]),
        )


if __name__ == "__main__":
    unittest.main()
