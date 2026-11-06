import subprocess
import os
import sys


def run_cli(input_data: str) -> str:
    script_path = os.path.join("projects", "line_number", "line_number.py")
    cmd = [sys.executable, script_path]
    result = subprocess.run(cmd, input=input_data.encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return result.stdout.decode()


import unittest


class TestLineNumber(unittest.TestCase):
    def test_multiple_lines(self):
        input_text = "first\nsecond\nthird\n"
        expected = "1\tfirst\n2\tsecond\n3\tthird\n"
        self.assertEqual(run_cli(input_text), expected)

    def test_empty_stream(self):
        self.assertEqual(run_cli("") , "")

    def test_last_line_no_newline(self):
        input_text = "foo\nbar"
        expected = "1\tfoo\n2\tbar"
        self.assertEqual(run_cli(input_text), expected)

