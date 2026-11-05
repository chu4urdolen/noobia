"""Unit tests for :mod:`idea_spark`.

The tests exercise the command line interface and the :func:`generate_prompt`
function from :mod:`projects.idea_spark.idea_spark`.

All tests are self‑contained and work regardless of the current working
directory thanks to :data:`sys.executable` and ``__file__``.
"""

import importlib
import os
import subprocess
import sys
import unittest


# Import the implementation.
from projects.idea_spark.idea_spark import generate_prompt


def run_cli(seed: int) -> tuple[str, str, int]:
    """Run the CLI with ``--seed`` and return stdout, stderr, exit code.

    The script path is resolved relative to this test file so the test works
    from any working directory.
    """
    script = os.path.join(os.path.dirname(__file__), "idea_spark.py")
    cmd = [sys.executable, script, "--seed", str(seed)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout.rstrip("\n"), result.stderr, result.returncode


class TestIdeaSpark(unittest.TestCase):
    def test_cli_matches_generator(self):
        stdout, stderr, rc = run_cli(7)
        self.assertEqual(rc, 0, "CLI should exit with code 0")
        self.assertEqual(stderr, "", "CLI should emit no stderr")
        self.assertEqual(stdout, generate_prompt(7), "Output must match generator")

    def test_reproducibility(self):
        out1, _, rc1 = run_cli(42)
        out2, _, rc2 = run_cli(42)
        self.assertEqual(rc1, 0)
        self.assertEqual(rc2, 0)
        self.assertEqual(out1, out2)

    def test_invalid_seed(self):
        # Passing a non‑integer should trigger argparse error.
        stdout, stderr, rc = run_cli("not_an_int")
        self.assertNotEqual(rc, 0, "CLI should fail with non‑int seed")
        self.assertIn("argument --seed", stderr, "stderr should mention the option")


if __name__ == "__main__":
    unittest.main()

