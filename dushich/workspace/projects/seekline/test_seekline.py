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

    def test_invalid_regex_json(self):
        """Verify that an invalid regex with ``--json`` still errors.

        The seekline tool should return a non‑zero exit code and emit an
        ``invalid regex`` message even when JSON output is requested.  The
        command line order ``--json [ pattern file`` is respected.
        """
        with tempfile.TemporaryDirectory() as td:
            fpath = os.path.join(td, "file.txt")
            with open(fpath, "w", encoding="utf-8") as f:
                f.write("foo\n")
            res = self.run_seekline("--json", "[", fpath)
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("invalid regex", res.stderr)

    def test_json_missing_file(self):
        """Run ``--json`` with a missing file and verify an error.

        The seekline tool should report a non‑zero exit code and a
        ``cannot open file`` message when a requested file does not exist.
        The JSON flag does not change this behaviour.
        """
        with tempfile.TemporaryDirectory() as td:
            # File path that will not be created
            fpath = os.path.join(td, "nonexistent.txt")
            res = self.run_seekline("--json", "foo", fpath)
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("cannot open file", res.stderr)

    def test_json_empty_file(self):
        """Run ``--json`` on an empty file.

        The command should exit with code 0, produce an empty JSON list, and
        emit no error output.
        """
        with tempfile.TemporaryDirectory() as td:
            fpath = os.path.join(td, "empty.txt")
            # create an empty file
            open(fpath, "w", encoding="utf-8").close()
            res = self.run_seekline("--json", "foo", fpath)
            self.assertEqual(res.returncode, 0)
            self.assertEqual(json.loads(res.stdout), [])
            self.assertEqual(res.stderr, "")

    def test_json_utf8_match(self):
        """Verify that JSON output correctly handles UTF‑8 text.

        The test creates a file containing a Greek word, runs ``--json`` with a
        pattern that matches that word, and checks that the returned JSON
        record contains the exact Unicode string and that no error is
        reported.
        """
        with tempfile.TemporaryDirectory() as td:
            fpath = os.path.join(td, "utf8.txt")
            greek = "κόσμε"  # Greek for "world"
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(f"{greek}\n")
            res = self.run_seekline("--json", greek, fpath)
            self.assertEqual(res.returncode, 0)
            data = json.loads(res.stdout)
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["text"], greek)
            self.assertEqual(res.stderr, "")

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

    def test_json_two_files(self):
        """Verify that JSON output aggregates matches from multiple files.

        The seekline CLI accepts one or more files.  When ``--json`` is
        supplied the implementation should return a list containing results
        from all files.  This regression test ensures that the results are
        collected in the order the files were passed on the command line.
        """
        with tempfile.TemporaryDirectory() as td:
            fpath1 = os.path.join(td, "file1.txt")
            fpath2 = os.path.join(td, "file2.txt")
            # File 1 contains one match on line 1.
            with open(fpath1, "w", encoding="utf-8") as f:
                f.write("foo bar\n")
            # File 2 contains two matches on lines 1 and 2.
            with open(fpath2, "w", encoding="utf-8") as f:
                f.write("foo baz\nfoo qux\n")
            res = self.run_seekline("--json", "foo", fpath1, fpath2)
            self.assertEqual(res.returncode, 0)
            data = json.loads(res.stdout)
            # Expect a list of 3 records in the order: file1 line1, file2 line1, file2 line2
            self.assertEqual(len(data), 3)
            self.assertEqual(data[0], {"path": fpath1, "line_number": 1, "text": "foo bar"})
            self.assertEqual(data[1], {"path": fpath2, "line_number": 1, "text": "foo baz"})
            self.assertEqual(data[2], {"path": fpath2, "line_number": 2, "text": "foo qux"})
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

    def test_json_ignore_case(self):
        """Verify JSON output when using ``--ignore-case``.

        The test file contains the words ``Foo`` and ``foo`` on
        separate lines.  The pattern ``FOO`` should match both lines when
        ``--ignore-case`` is specified.  The output should be a JSON
        array with two objects, each containing the correct ``path``,
        ``line_number`` and ``text`` values.
        """
        with tempfile.TemporaryDirectory() as td:
            fpath = os.path.join(td, "case.txt")
            with open(fpath, "w", encoding="utf-8") as f:
                f.write("Foo\nfoo\n")
            res = self.run_seekline("--json", "--ignore-case", "FOO", fpath)
            self.assertEqual(res.returncode, 0)
            data = json.loads(res.stdout)
            self.assertEqual(len(data), 2)
            # Verify that both entries are present and correct.
            expected = {
                1: {"path": fpath, "line_number": 1, "text": "Foo"},
                2: {"path": fpath, "line_number": 2, "text": "foo"},
            }
            for entry in data:
                self.assertIn(entry["line_number"], expected)
                self.assertEqual(entry, expected[entry["line_number"]])
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

