import subprocess
import json
import os
import sys
import tempfile
import unittest

class TestWordCount(unittest.TestCase):
    def run_wordcount(self, file_path):
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'wordcount.py'))
        return subprocess.run([
            sys.executable,
            script_path,
            file_path
        ], capture_output=True, text=True)

    def test_normal_counting(self):
        txt = "Hello world\nHello again"
        with tempfile.TemporaryDirectory() as tmp:
            file_path = os.path.join(tmp, 'sample.txt')
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(txt)
            res = self.run_wordcount(file_path)
        self.assertEqual(res.returncode, 0)
        counts = json.loads(res.stdout)
        self.assertEqual(counts, {"again":1, "hello":2, "world":1})

    def test_case_folding(self):
        txt = "Apple apple APPLE"
        with tempfile.TemporaryDirectory() as tmp:
            file_path = os.path.join(tmp, 'sample.txt')
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(txt)
            res = self.run_wordcount(file_path)
        self.assertEqual(res.returncode, 0)
        counts = json.loads(res.stdout)
        self.assertEqual(counts, {"apple":3})

    def test_missing_file(self):
        missing = os.path.join('does_not_exist.txt')
        res = self.run_wordcount(missing)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("not found", res.stderr)

    def test_german_casefolding(self):
        # German "ß" should fold to "ss"; both variations count together.
        txt = "Straße STRASSE"
        with tempfile.TemporaryDirectory() as tmp:
            file_path = os.path.join(tmp, 'sample.txt')
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(txt)
            res = self.run_wordcount(file_path)
            self.assertEqual(res.returncode, 0)
            counts = json.loads(res.stdout)
            # Both should be counted as "strasse"
            self.assertEqual(counts, {"strasse":2})

    def test_tokenization_punctuation(self):
        # Words adjacent to punctuation should be tokenized correctly.
        txt = "Hello, hello!"
        with tempfile.TemporaryDirectory() as tmp:
            file_path = os.path.join(tmp, 'sample.txt')
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(txt)
            res = self.run_wordcount(file_path)
        self.assertEqual(res.returncode, 0)
        counts = json.loads(res.stdout)
        self.assertEqual(counts, {"hello": 2})

if __name__ == "__main__":
    unittest.main()
