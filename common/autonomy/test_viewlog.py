"""viewlog: tests never write to live views; production never imports unittest."""

import ast
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import viewlog  # noqa: E402

PRODUCTION = [p for p in HERE.rglob("*.py") if not p.name.startswith("test_")]


class ViewlogTest(unittest.TestCase):
    def test_under_unittest_lines_are_captured_not_logged(self):
        with mock.patch.dict(os.environ, {}, clear=False), \
                mock.patch.object(viewlog.syslog, "syslog") as real:
            os.environ.pop("NOOBIA_VIEWS_SINK", None)
            self.assertFalse(viewlog.write("noobia-sense", "NOOBIA P1 test x | y"))
            real.assert_not_called()
        self.assertIn(("noobia-sense", "NOOBIA P1 test x | y"), viewlog.CAPTURED)

    def test_explicit_syslog_sink_writes(self):
        with mock.patch.dict(os.environ, {"NOOBIA_VIEWS_SINK": "syslog"}), \
                mock.patch.object(viewlog.syslog, "openlog"), \
                mock.patch.object(viewlog.syslog, "closelog"), \
                mock.patch.object(viewlog.syslog, "syslog") as real:
            self.assertTrue(viewlog.write("noobia-sense", "line"))
            real.assert_called_once()

    def test_production_process_defaults_to_syslog(self):
        code = ("import sys; sys.path.insert(0, %r); import viewlog; print(viewlog.sink())" % str(HERE))
        env = {k: v for k, v in os.environ.items() if k != "NOOBIA_VIEWS_SINK"}
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                             timeout=10, env=env).stdout.strip()
        self.assertEqual(out, "syslog")

    def test_no_production_module_imports_unittest(self):
        for path in PRODUCTION:
            tree = ast.parse(path.read_text(), str(path))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                for name in names:
                    self.assertFalse(name.split(".")[0] == "unittest", f"{path} imports {name}")

    def test_no_production_module_calls_syslog_directly(self):
        for path in PRODUCTION:
            if path.name == "viewlog.py":
                continue
            self.assertFalse("syslog.syslog(" in path.read_text(), f"{path.name} bypasses viewlog")


if __name__ == "__main__":
    unittest.main()
