import json
import subprocess
import sys
import os
import unittest

class TestLedger(unittest.TestCase):
    def run_ledger(self, csv_content: str):
        import tempfile
        with tempfile.NamedTemporaryFile('w', delete=False, suffix='.csv') as f:
            f.write(csv_content)
            tmp = f.name
        try:
            result = subprocess.run([sys.executable, '-m', 'projects.mini_ledgers.ledger', tmp],
                                     capture_output=True, text=True, check=False)
            return result
        finally:
            os.unlink(tmp)

    def test_basic(self):
        csv = """Alice,10.5
Bob,5
Alice,4.5"""
        res = self.run_ledger(csv)
        self.assertEqual(res.returncode, 0)
        out = json.loads(res.stdout)
        self.assertEqual(out, {'Alice': '15.0', 'Bob': '5'})

    def test_invalid_amount(self):
        csv = """Alice,foo"""
        res = self.run_ledger(csv)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn('invalid amount', res.stderr.lower())

    def test_non_finite_amount(self):
        # Use a Decimal string that represents Infinity
        csv = """Alice,Infinity"""
        res = self.run_ledger(csv)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn('non‑finite amount', res.stderr.lower())

    def test_missing_file(self):
        res = subprocess.run([sys.executable, '-m', 'projects.mini_ledgers.ledger', 'nonexistent.csv'],
                             capture_output=True, text=True)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn('file', res.stderr.lower())

    def test_edge_case_empty_lines(self):
        csv = """\nAlice,1\n\nBob,2"""
        res = self.run_ledger(csv)
        self.assertEqual(res.returncode, 0)
        out = json.loads(res.stdout)
        self.assertEqual(out, {'Alice': '1', 'Bob': '2'})

    def test_exact_decimal_addition(self):
        # 0.1 + 0.2 == 0.3 exactly with Decimal
        csv = """Alice,0.1
Alice,0.2"""
        res = self.run_ledger(csv)
        self.assertEqual(res.returncode, 0)
        out = json.loads(res.stdout)
        self.assertEqual(out, {'Alice': '0.3'})

    def test_three_columns(self):
        """A row with three columns should cause an error.

        The ledger expects exactly two columns: name and amount. A row
        containing an additional field should trigger a ``ValueError`` from
        :func:`read_csv`, which is then printed to ``stderr`` and causes the
        script to exit with status 1.
        """
        csv = """Alice,10,5"""
        res = self.run_ledger(csv)
        # The program should exit with a non-zero status
        self.assertNotEqual(res.returncode, 0)
        # The error message should mention the column count mismatch
        self.assertIn('expected 2 columns', res.stderr.lower())

if __name__ == '__main__':
    unittest.main()
