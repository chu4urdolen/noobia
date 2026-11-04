#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import tempfile
import unittest


class TestSeekline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = os.path.join(os.path.dirname(__file__), "seekline.py")

    def run_seekline(self, *args, cwd=None):
        cmd = [sys.executable, self.script] + list(args)
        return subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
        )

    def test_normal_match(self):
        with tempfile.TemporaryDirectory() as td:
            fpath = os.path.join(td, "file.txt")
            with open(fpath, "w", encoding="utf-8") as f:
                f.write("foo bar\nbaz\nFoo\n")
            res = self.run_seekline("foo", fpath)
            self.assertEqual(res.returncode, 0)
            self.assertEqual(
                res.stdout.strip(),
                f"{fpath}:1:foo bar",
            )
            self.assertEqual(res.stderr, "")

    def test_ignore_case(self):
        with tempfile.TemporaryDirectory() as td:
            fpath = os.path.join(td, "file.txt")
            with open(fpath, "w", encoding="utf-8") as f:
                f.write("foo bar\nbaz\nFoo\n")
            res = self.run_seekline("--ignore-case", "FOO", fpath)
            self.assertEqual(res.returncode, 0)
            self.assertEqual(
                res.stdout.strip(),
                f"{fpath}:1:foo bar\n{fpath}:3:Foo",
            )
            self.assertEqual(res.stderr, "")

    def test_json_output(self):
        with tempfile.TemporaryDirectory() as td:
            fpath = os.path.join(td, "file.txt")
            with open(fpath, "w", encoding="utf-8") as f:
                f.write("foo bar\nbaz\nFoo\n")
            res = self.run_seekline("--json", "foo", fpath)
            self.assertEqual(res.returncode, 0)
            data = json.loads(res.stdout)
            self.assertEqual(len(data), 1)
            self.assertEqual(
                data[0],
                {"path": fpath, "line_number": 1, "text": "foo bar"},
            )
            self.assertEqual(res.stderr, "")

    def test_trailing_spaces_preserved(self):
        """Ensure that lines ending with spaces are not truncated.

        The previous implementation used ``line.rstrip()`` which removes
        whitespace characters including trailing spaces.  This test writes a
        line that ends with a space and verifies that the space is still
        present in both plain‑text and JSON output.
        """
        with tempfile.TemporaryDirectory() as td:
            fpath = os.path.join(td, "file.txt")
            # line ends with a single space
            with open(fpath, "w", encoding="utf-8") as f:
                f.write("foo bar \n")
            res = self.run_seekline("foo", fpath)
            self.assertEqual(res.returncode, 0)
            # ``strip()`` removes the trailing space, which is exactly what
            # we want to preserve.  ``rstrip("\n")`` removes only the final
            # newline, leaving the space intact.
            self.assertEqual(res.stdout.rstrip("\n"), f"{fpath}:1:foo bar ")
            self.assertEqual(res.stderr, "")

            res_json = self.run_seekline("--json", "foo", fpath)
            self.assertEqual(res_json.returncode, 0)
            data = json.loads(res_json.stdout)
            self.assertEqual(data[0]["text"], "foo bar ")

    def test_crlf_line_ending(self):
        """Verify that CRLF line endings are handled correctly.

        The program opens files in text mode with UTF‑8 encoding, which
        automatically normalises line endings on Windows.  However the
        ``cleaned`` value removes only ``\r`` and ``\n`` characters.  This
        test writes a file with explicit CRLF endings and ensures that the
        output contains the text without the line‑ending characters.
        """
        with tempfile.TemporaryDirectory() as td:
            fpath = os.path.join(td, "file.txt")
            # Write a line with CRLF. ``open(..., newline='')`` keeps the
            # characters verbatim.
            with open(fpath, "w", encoding="utf-8", newline='') as f:
                f.write("foo bar\r\n")
            res = self.run_seekline("foo", fpath)
            self.assertEqual(res.returncode, 0)
            self.assertEqual(res.stdout.strip(), f"{fpath}:1:foo bar")
            self.assertEqual(res.stderr, "")

    def test_invalid_regex(self):
        with tempfile.TemporaryDirectory() as td:
            fpath = os.path.join(td, "file.txt")
            with open(fpath, "w", encoding="utf-8") as f:
                f.write("foo\n")
            res = self.run_seekline("[", fpath)
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("invalid regex", res.stderr)

    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as td:
            fpath = os.path.join(td, "nonexistent.txt")
            res = self.run_seekline("foo", fpath)
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("cannot open file", res.stderr)

    def test_no_matches(self):
        with tempfile.TemporaryDirectory() as td:
            fpath = os.path.join(td, "file.txt")
            with open(fpath, "w", encoding="utf-8") as f:
                f.write("bar\nbaz\n")
            res = self.run_seekline("xyz", fpath)
            self.assertEqual(res.returncode, 0)
            self.assertEqual(res.stdout, "")
            self.assertEqual(res.stderr, "")

    def test_json_no_matches(self):
        """Ensure ``--json`` correctly returns an empty list when no matches
        are found.  The command should still exit with code 0 and emit no
        error output.
        """
        with tempfile.TemporaryDirectory() as td:
            fpath = os.path.join(td, "file.txt")
            with open(fpath, "w", encoding="utf-8") as f:
                f.write("bar\nbaz\n")
            res = self.run_seekline("--json", "xyz", fpath)
            self.assertEqual(res.returncode, 0)
            # JSON output is a list; for no matches it should be empty.
            self.assertEqual(json.loads(res.stdout), [])
            self.assertEqual(res.stderr, "")

    def test_json_multiple_files(self):
        """Verify JSON output when searching multiple files.

        Two temporary files each contain a single matching line.  The
        command should output a JSON array with two objects, each
        containing the correct ``path``, ``line_number``, and ``text``.
        ``stderr`` must be empty and the exit code should be ``0``.
        """
        with tempfile.TemporaryDirectory() as td:
            f1 = os.path.join(td, "a.txt")
            f2 = os.path.join(td, "b.txt")
            # Write a single matching line in each file.
            for fp in (f1, f2):
                with open(fp, "w", encoding="utf-8") as f:
                    f.write("foo\n")
            res = self.run_seekline("--json", "foo", f1, f2)
            self.assertEqual(res.returncode, 0)
            data = json.loads(res.stdout)
            self.assertEqual(len(data), 2)
            # Verify that each entry matches the expected values.
            expected = {
                f1: {"path": f1, "line_number": 1, "text": "foo"},
                f2: {"path": f2, "line_number": 1, "text": "foo"},
            }
            for entry in data:
                self.assertIn(entry["path"], expected)
                self.assertEqual(entry, expected[entry["path"]])
            self.assertEqual(res.stderr, "")

    def test_multiple_files(self):
        with tempfile.TemporaryDirectory() as td:
            f1 = os.path.join(td, "a.txt")
            f2 = os.path.join(td, "b.txt")
            for fp in (f1, f2):
                with open(fp, "w", encoding="utf-8") as f:
                    f.write("foo\n")
            res = self.run_seekline("foo", f1, f2)
            self.assertEqual(res.returncode, 0)
            out_lines = res.stdout.strip().splitlines()
            self.assertIn(f"{f1}:1:foo", out_lines)
            self.assertIn(f"{f2}:1:foo", out_lines)

    def test_empty_pattern(self):
        with tempfile.TemporaryDirectory() as td:
            fpath = os.path.join(td, "file.txt")
            with open(fpath, "w", encoding="utf-8") as f:
                f.write("foo\n")
            res = self.run_seekline("", fpath)
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("Pattern cannot be empty", res.stderr)


if __name__ == "__main__":
    unittest.main()

