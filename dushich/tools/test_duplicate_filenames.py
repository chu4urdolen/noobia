#!/usr/bin/env python3
"""Tests for the duplicate_filenames reporter.

Run with:  python3 -m unittest discover -s projects/duplicate_names -q

The tests cover:
  * duplicate grouping by basename (not content),
  * ignoring of ``.git`` directories and symlinked directories,
  * exclusion of non-regular files (symlinks),
  * recording of permission errors,
  * deterministic, fully sorted JSON reports,
  * the start/status/result CLI: bounded plain text, private state
    directory, and non-blocking (detached) behaviour.

Only the Python standard library is used.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import duplicate_filenames as df  # noqa: E402

MODULE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "duplicate_filenames.py")


def run_cli(*args, env=None, timeout=25.0):
    """Run the CLI in a subprocess; return (CompletedProcess, elapsed_s)."""
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    started = time.monotonic()
    proc = subprocess.run(
        [sys.executable, MODULE] + list(args),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=full_env,
    )
    return proc, time.monotonic() - started


def write(path, content="x\n"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


def wait_for_terminal_status(job, state, timeout=45.0):
    """Poll ``status`` until the job is completed or failed (bounded)."""
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last, _ = run_cli("status", job, "--dir", state)
        if "status=completed" in last.stdout or "status=failed" in last.stdout:
            return last
        time.sleep(0.1)
    assert last is not None
    return last


def make_tree(root):
    """Build a tree with known duplicates plus the tricky edge cases.

    Returns the path of the *outside* directory reachable only through a
    symlinked directory.
    """
    # Three copies of report.txt in different locations -> one duplicate group.
    write(os.path.join(root, "a", "report.txt"))
    write(os.path.join(root, "a", "deep", "report.txt"))
    write(os.path.join(root, "b", "report.txt"))
    # Unique files.
    write(os.path.join(root, "b", "notes.md"))
    write(os.path.join(root, "unique.txt"))
    # A real .git directory that must be ignored.
    write(os.path.join(root, ".git", "config"))
    write(os.path.join(root, ".git", "objects", "pack", "idx"))
    # A symlinked directory that must not be traversed.
    outside = root + "_outside"
    write(os.path.join(outside, "report.txt"))
    os.symlink(outside, os.path.join(root, "linked_dir"))
    # A symlink to a file: not a regular file, must not be counted.
    os.symlink(os.path.join(root, "unique.txt"),
               os.path.join(root, "b", "unique_link.txt"))
    return outside


class ScanTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = os.path.join(self._tmp.name, "root")
        self.outside = make_tree(self.root)

    def all_paths(self, groups):
        return sorted(p for paths in groups.values() for p in paths)


class TestScanGrouping(ScanTestCase):
    def test_groups_by_basename(self):
        groups, errors, scanned = df.scan_tree(self.root)
        self.assertEqual(errors, [])
        self.assertEqual(scanned, 5)
        report = df.build_report(self.root, groups, errors, scanned)
        dups = report["duplicates"]
        self.assertEqual(sorted(dups), ["report.txt"])
        self.assertEqual(dups["report.txt"], sorted([
            os.path.join(self.root, "a", "report.txt"),
            os.path.join(self.root, "a", "deep", "report.txt"),
            os.path.join(self.root, "b", "report.txt"),
        ]))
        self.assertEqual(report["duplicate_basenames"], 1)
        self.assertEqual(report["unique_basenames"], 3)
        self.assertEqual(report["scanned_files"], 5)

    def test_grouping_ignores_content(self):
        # Different content, same basename -> still one duplicate group.
        write(os.path.join(self.root, "c", "data.log"), "one\n")
        write(os.path.join(self.root, "d", "data.log"), "entirely different\n")
        groups, _, _ = df.scan_tree(self.root)
        self.assertEqual(len(groups["data.log"]), 2)
        report = df.build_report(self.root, groups, [], 7)
        self.assertEqual(sorted(report["dups" if False else "duplicates"]),
                         ["data.log", "report.txt"])

    def test_unique_files_not_in_duplicates(self):
        groups, _, scanned = df.scan_tree(self.root)
        report = df.build_report(self.root, groups, [], scanned)
        self.assertNotIn("unique.txt", report["duplicates"])
        self.assertNotIn("notes.md", report["duplicates"])


class TestExclusions(ScanTestCase):
    def test_git_dir_ignored(self):
        groups, errors, _ = df.scan_tree(self.root)
        self.assertEqual(errors, [])
        for p in self.all_paths(groups):
            self.assertNotIn(os.sep + ".git" + os.sep, p)
        self.assertNotIn("config", groups)
        self.assertNotIn("idx", groups)

    def test_symlinked_dir_not_traversed(self):
        groups, _, scanned = df.scan_tree(self.root)
        flat = self.all_paths(groups)
        self.assertNotIn(os.path.join(self.outside, "report.txt"), flat)
        self.assertEqual(len(groups["report.txt"]), 3)
        self.assertEqual(scanned, 5)

    def test_symlink_file_not_counted(self):
        groups, _, _ = df.scan_tree(self.root)
        self.assertNotIn("unique_link.txt", groups)


class TestPermissionErrors(ScanTestCase):
    def test_permission_error_recorded(self):
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("running as root; permission errors cannot be triggered")
        secret = os.path.join(self.root, "secret")
        write(os.path.join(secret, "hidden.txt"))
        os.chmod(secret, 0o000)
        try:
            groups, errors, scanned = df.scan_tree(self.root)
        finally:
            os.chmod(secret, 0o755)
        self.assertEqual(len(errors), 1)
        self.assertIn("PermissionError", errors[0]["error"])
        self.assertIn("secret", errors[0]["path"])
        self.assertNotIn("hidden.txt", groups)
        # The scan still covered the rest of the tree.
        self.assertEqual(scanned, 5)


class TestSortedReport(ScanTestCase):
    def test_lists_sorted_and_only_duplicates_present(self):
        groups, errors, scanned = df.scan_tree(self.root)
        report = df.build_report(self.root, groups, errors, scanned)
        for name, paths in report["duplicates"].items():
            self.assertEqual(paths, sorted(paths))
            self.assertGreaterEqual(len(paths), 2)
        self.assertEqual(report["permission_errors"],
                         sorted(report["permission_errors"],
                                key=lambda e: (e["path"], e["error"])))

    def test_rendered_report_is_sorted_json(self):
        groups, errors, scanned = df.scan_tree(self.root)
        report = df.build_report(self.root, groups, errors, scanned)
        rendered = json.dumps(report, indent=2, sort_keys=True)
        self.assertEqual(rendered,
                         json.dumps(json.loads(rendered), indent=2, sort_keys=True))


class TestCli(ScanTestCase):
    def setUp(self):
        super().setUp()
        self.state = os.path.join(self._tmp.name, "state")

    def test_start_returns_job_id_and_completes(self):
        proc, _ = run_cli("start", self.root, "--dir", self.state)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(len(proc.stdout.strip().splitlines()), 1)
        job = proc.stdout.strip()
        self.assertRegex(job, r"^[0-9a-f]{12}$")
        final = wait_for_terminal_status(job, self.state)
        self.assertIn("status=completed", final.stdout)
        self.assertIn("files=5", final.stdout)
        self.assertIn("duplicates=1", final.stdout)
        self.assertIn("errors=0", final.stdout)

    def test_status_is_bounded_single_line(self):
        proc, _ = run_cli("start", self.root, "--dir", self.state)
        job = proc.stdout.strip()
        wait_for_terminal_status(job, self.state)
        res, _ = run_cli("status", job, "--dir", self.state)
        self.assertEqual(res.returncode, 0)
        lines = res.stdout.strip().splitlines()
        self.assertEqual(len(lines), 1)  # strictly bounded plain text
        self.assertIn("status=completed", lines[0])

    def test_status_not_found(self):
        proc, _ = run_cli("status", "deadbeef0000", "--dir", self.state)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("not-found", proc.stdout)
        self.assertEqual(len(proc.stdout.strip().splitlines()), 1)

    def test_result_lists_sorted_duplicates(self):
        proc, _ = run_cli("start", self.root, "--dir", self.state)
        job = proc.stdout.strip()
        wait_for_terminal_status(job, self.state)
        res, _ = run_cli("result", job, "--dir", self.state)
        self.assertEqual(res.returncode, 0)
        self.assertIn("report.txt (3):", res.stdout)
        expected = sorted([
            os.path.join(self.root, "a", "report.txt"),
            os.path.join(self.root, "a", "deep", "report.txt"),
            os.path.join(self.root, "b", "report.txt"),
        ])
        shown = re.findall(r"^\s+- (\S+)$", res.stdout, flags=re.M)
        self.assertEqual(shown, expected)

    def test_result_report_file_is_sorted_json(self):
        proc, _ = run_cli("start", self.root, "--dir", self.state)
        job = proc.stdout.strip()
        wait_for_terminal_status(job, self.state)
        res, _ = run_cli("result", job, "--dir", self.state)
        match = re.search(r"report=(\S+)", res.stdout)
        self.assertIsNotNone(match)
        with open(match.group(1), "r", encoding="utf-8") as report_file:
            text = report_file.read()
        data = json.loads(text)
        self.assertEqual(text, json.dumps(data, indent=2, sort_keys=True) + "\n")
        self.assertEqual(data["duplicates"]["report.txt"],
                         sorted(data["duplicates"]["report.txt"]))

    def test_result_bounded_by_max(self):
        many = os.path.join(self._tmp.name, "many")
        for i in range(30):
            name = "file_%02d.txt" % i
            write(os.path.join(many, "d%02d" % i, name))
            write(os.path.join(many, "e%02d" % i, name))
        proc, _ = run_cli("start", many, "--dir", self.state)
        job = proc.stdout.strip()
        wait_for_terminal_status(job, self.state)
        res, _ = run_cli("result", job, "--dir", self.state, "--max", "5")
        self.assertEqual(res.returncode, 0)
        self.assertIn("duplicates (30 total):", res.stdout)
        groups_shown = re.findall(r"^  \S+ \(\d+\):$", res.stdout, flags=re.M)
        self.assertEqual(len(groups_shown), 5)
        self.assertIn("... 25 more", res.stdout)
        # Output stays bounded: at most 5 groups x 2 paths + a few meta lines.
        self.assertLessEqual(len(res.stdout.splitlines()), 20)

    def test_result_caps_paths_within_one_duplicate_group(self):
        many = os.path.join(self._tmp.name, "many-paths")
        for i in range(25):
            write(os.path.join(many, "d%02d" % i, "shared.txt"))
        proc, _ = run_cli("start", many, "--dir", self.state)
        job = proc.stdout.strip()
        wait_for_terminal_status(job, self.state)
        res, _ = run_cli("result", job, "--dir", self.state,
                         "--max", "1", "--max-paths", "3")
        self.assertEqual(res.returncode, 0)
        self.assertIn("shared.txt (25):", res.stdout)
        self.assertEqual(len(re.findall(r"^    - ", res.stdout, flags=re.M)), 3)
        self.assertIn("... 22 more paths", res.stdout)

    def test_state_dir_is_private(self):
        proc, _ = run_cli("start", self.root, "--dir", self.state)
        job = proc.stdout.strip()
        wait_for_terminal_status(job, self.state)
        self.assertEqual(os.stat(self.state).st_mode & 0o777, 0o700)
        job_file = os.path.join(self.state, "jobs", job + ".json")
        self.assertEqual(os.stat(job_file).st_mode & 0o777, 0o600)
        report_file = os.path.join(self.state, "reports", job + ".json")
        self.assertEqual(os.stat(report_file).st_mode & 0o777, 0o600)

    def test_failed_job_is_reported(self):
        missing = os.path.join(self._tmp.name, "does-not-exist")
        proc, _ = run_cli("start", missing, "--dir", self.state)
        self.assertEqual(proc.returncode, 0)  # start is non-blocking
        job = proc.stdout.strip()
        final = wait_for_terminal_status(job, self.state)
        self.assertIn("status=failed", final.stdout)
        self.assertIn("FileNotFoundError", final.stdout)
        res, _ = run_cli("result", job, "--dir", self.state)
        self.assertEqual(res.returncode, 3)
        self.assertIn("error=", res.stdout)


class TestNonBlocking(ScanTestCase):
    """start/status/result must never block on the scan itself."""

    def setUp(self):
        super().setUp()
        self.state = os.path.join(self._tmp.name, "state")
        # Make the worker scan take a deterministic, measurable amount of time.
        self.delay = 4.0
        self.delay_env = {df.TEST_WORKER_DELAY_ENV: str(self.delay)}

    def test_start_returns_before_scan_completes(self):
        proc, elapsed = run_cli("start", self.root, "--dir", self.state,
                                env=self.delay_env)
        self.assertEqual(proc.returncode, 0)
        job = proc.stdout.strip()
        self.assertRegex(job, r"^[0-9a-f]{12}$")
        # If start blocked on the scan it would take at least `delay` seconds;
        # it must return well before that.
        self.assertLess(elapsed, self.delay * 0.75)
        # ... and the job must not already be finished.
        status_out, _ = run_cli("status", job, "--dir", self.state)
        self.assertNotIn("status=completed", status_out.stdout)
        self.assertNotIn("status=failed", status_out.stdout)
        # Let the detached worker finish so no stray process outlives the test.
        final = wait_for_terminal_status(job, self.state)
        self.assertIn("status=completed", final.stdout)

    def test_status_and_result_are_nonblocking_while_running(self):
        proc, _ = run_cli("start", self.root, "--dir", self.state,
                          env=self.delay_env)
        job = proc.stdout.strip()
        t0 = time.monotonic()
        status_out, _ = run_cli("status", job, "--dir", self.state)
        result_out, _ = run_cli("result", job, "--dir", self.state)
        elapsed = time.monotonic() - t0
        # Both commands must return promptly (they only read state files).
        self.assertLess(elapsed, self.delay * 0.75)
        self.assertIn("status=", status_out.stdout)
        self.assertNotIn("status=completed", status_out.stdout)
        self.assertIn("result not available yet", result_out.stdout)
        # result of an unfinished job exits 2 (not completed)
        # (re-run to inspect the exit code explicitly)
        res, _ = run_cli("result", job, "--dir", self.state)
        self.assertEqual(res.returncode, 2)
        final = wait_for_terminal_status(job, self.state)
        self.assertIn("status=completed", final.stdout)


if __name__ == "__main__":
    unittest.main()
