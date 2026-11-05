#!/usr/bin/env python3
"""Environment probe script.

This script performs a lightweight smoke‑check of the runtime environment.
It verifies the following aspects:

* The Python interpreter version (must be 3.6 or newer).
* Successful import of a standard‑library module (``json``).
* Availability of the ``git`` executable and its ability to report a version.
* Ability to create a temporary file, write to it, and read it back.

The results are emitted as a JSON object with boolean ``pass`` values for
each check.  If any check fails, the script exits with a non‑zero status.
"""

import json
import os
import subprocess
import sys
import tempfile


def check_python_version() -> bool:
    """Return ``True`` if the Python version is >= 3.6."""
    return sys.version_info >= (3, 6)


def check_stdlib_import() -> bool:
    """Return ``True`` if the ``json`` module imports successfully."""
    try:
        import json  # noqa: F401
        return True
    except Exception:
        return False


def check_git_executable() -> bool:
    """Return ``True`` if ``git --version`` runs successfully.

    The command must exit with status 0 and produce output containing the
    word ``git``.
    """
    try:
        result = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True,
            check=True,
        )
        return "git" in result.stdout.lower()
    except Exception:
        return False


def check_temp_file_access() -> bool:
    """Return ``True`` if a temp file can be created, written to, and read.

    The function uses ``tempfile.TemporaryDirectory`` to guarantee cleanup.
    """
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = os.path.join(tmpdir, "probe.txt")
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write("test")
            with open(temp_path, "r", encoding="utf-8") as f:
                content = f.read()
            return content == "test"
    except Exception:
        return False


def main() -> None:
    results = {
        "python_version": check_python_version(),
        "stdlib_import": check_stdlib_import(),
        "git_executable": check_git_executable(),
        "temp_file": check_temp_file_access(),
    }
    # Emit JSON to stdout.
    json.dump(results, sys.stdout)
    sys.stdout.flush()
    # Non‑zero exit if any check failed.
    if not all(results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()

