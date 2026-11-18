"""Unit tests for summarizer/compact_output.py."""

import unittest

from compact_output import (
    compact_task_report,
    compact_test_output,
    extract_final_codex_reply,
)


class TestExtractFinalCodexReply(unittest.TestCase):
    def test_extracts_after_codex_marker_and_strips_tokens_tail(self):
        raw = (
            "some noise\n"
            "codex\n"
            "Done. The thing works.\n"
            "\ntokens used\n1234\n"
        )
        self.assertEqual(extract_final_codex_reply(raw), "Done. The thing works.")

    def test_falls_back_to_last_dash_header_and_truncates(self):
        raw = "earlier text\n--------\n" + ("x" * 100) + "\n"
        out = extract_final_codex_reply(raw, max_chars=40)
        self.assertEqual(len(out), 40)
        self.assertEqual(out, "x" * 40)

    def test_plain_text_returns_stripped_input(self):
        self.assertEqual(extract_final_codex_reply("  hello  \n"), "hello")


class TestCompactTestOutput(unittest.TestCase):
    def test_ok_run_becomes_one_line(self):
        out = (
            "test_a ... ok\n"
            "test_b ... ok\n"
            "----------------------------------------------------------------------\n"
            "Ran 2 tests in 0.001s\n"
            "\n"
            "OK\n"
        )
        self.assertEqual(compact_test_output(out, exit_code=0), "Ran 2 tests in 0.001s (OK)")

    def test_failure_returns_tail(self):
        out = "test_a ... FAIL\n" + ("traceback " * 100)
        compacted = compact_test_output(out, exit_code=1, max_fail_chars=50)
        self.assertEqual(len(compacted), 50)
        self.assertEqual(compacted, out.strip()[-50:])

    def test_output_without_separator_uses_last_line(self):
        out = "line one\nline two\n"
        self.assertEqual(compact_test_output(out), "line two")


class TestCompactTaskReport(unittest.TestCase):
    def test_drops_test_lines_keeps_headers_and_caps_report(self):
        raw = (
            "Dushich task: do the thing\n"
            "Attempts: 1\n"
            "Git HEAD: abc1234\n"
            "Test exit: 0\n"
            "Dushich's report:\n"
            "--------\n"
            "test_a ... ok\n"
            "test_b ... ok\n"
            "Done. The thing works and is verified end to end.\n"
            "Thread: t1\n"
        )
        out = compact_task_report(raw)
        self.assertIn("Dushich task: do the thing", out)
        self.assertIn("Thread: t1", out)
        self.assertNotIn("test_a", out)
        self.assertNotIn("--------", out)
        self.assertIn(
            "Dushich's report: Done. The thing works and is verified end to end.",
            out,
        )

    def test_report_text_is_capped(self):
        raw = "Dushich's report: " + "y" * 500
        out = compact_task_report(raw, max_reply_chars=100)
        self.assertTrue(out.endswith("y" * 100))
        self.assertLessEqual(len(out.splitlines()[-1]), len("Dushich's report: ") + 100)

    def test_no_report_section_leaves_headers(self):
        raw = "Dushich task: x\nTest exit: 1\n"
        self.assertEqual(compact_task_report(raw), "Dushich task: x\nTest exit: 1")


if __name__ == "__main__":
    unittest.main()
