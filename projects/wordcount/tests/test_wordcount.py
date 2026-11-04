import subprocess, json, os, sys
import unittest

class TestWordCount(unittest.TestCase):
    def run_wordcount(self, file_path):
        return subprocess.run([
            sys.executable,
            os.path.join(os.path.dirname(__file__), '..', 'wordcount.py'),
            file_path
        ], capture_output=True, text=True)

    def test_normal_counting(self):
        txt = "Hello world\nHello again"
        with open('sample.txt', 'w', encoding='utf-8') as f:
            f.write(txt)
        res = self.run_wordcount('sample.txt')
        os.remove('sample.txt')
        self.assertEqual(res.returncode, 0)
        counts = json.loads(res.stdout)
        self.assertEqual(counts, {"again":1, "hello":2, "world":1})

    def test_case_folding(self):
        txt = "Apple apple APPLE"
        with open('sample.txt', 'w', encoding='utf-8') as f:
            f.write(txt)
        res = self.run_wordcount('sample.txt')
        os.remove('sample.txt')
        self.assertEqual(res.returncode, 0)
        counts = json.loads(res.stdout)
        self.assertEqual(counts, {"apple":3})

    def test_missing_file(self):
        missing = 'does_not_exist.txt'
        res = self.run_wordcount(missing)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("not found", res.stderr)

if __name__ == "__main__":
    unittest.main()
