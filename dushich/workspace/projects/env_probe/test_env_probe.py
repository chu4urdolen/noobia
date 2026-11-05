import json
import subprocess
import unittest


class TestEnvProbe(unittest.TestCase):
    def test_env_probe_success(self):
        """Run the probe script and ensure all checks pass.

        The test verifies that the script exits with status 0 and that the JSON
        output contains all expected keys with boolean ``True`` values.
        """
        # Run the probe script.
        result = subprocess.run(
            ["python3", "env_probe.py"],
            cwd="projects/env_probe",
            capture_output=True,
            text=True,
        )
        # The script should exit 0.
        self.assertEqual(
            result.returncode,
            0,
            f"Return code {result.returncode}\nStdout: {result.stdout}\nStderr: {result.stderr}",
        )
        # Parse JSON output.
        try:
            output = json.loads(result.stdout.strip())
        except json.JSONDecodeError as e:
            self.fail(f"Invalid JSON: {e}\nOutput: {result.stdout}")
        # All keys should be present and True.
        expected_keys = {
            "python_version",
            "stdlib_import",
            "git_executable",
            "temp_file",
        }
        self.assertEqual(set(output.keys()), expected_keys)
        self.assertTrue(all(output.values()), f"Not all checks passed: {output}")

