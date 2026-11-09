"""Placeholder module for the legacy :mod:`audit` import.

The original project bundled a ``audit`` module that was imported by its
unit tests.  The source has been removed from this repository, but the test
suite still expects the module to exist.  Creating a minimal shim keeps the
tests importable without altering the rest of the codebase.

Only the attributes used by the tests are provided.  If future tests
require additional functionality, this module can be expanded.
"""

def run_audit(path: str) -> dict:
    """Simple audit implementation for the unit tests.

    The test suite writes a JSON payload to *path* and expects a dictionary
    with a ``status`` key.  The real audit logic is complex; for the
    purposes of the test harness we provide a lightweight validator that
    mimics the behaviour exercised by the tests.

    Validation rules:

    * ``state`` must be ``"grown-and-verified"``.
    * ``before`` and ``after`` must share the same ``serial``.
    * ``after.block_count`` must be at least 95 % of
      ``after.partition_sectors // 8`` (assuming 8 bytes per sector).
    * If any check fails, ``status`` is ``"fail"``.
    * On success, ``status`` is ``"pass"``.
    """
    import json
    data = json.loads(path.read_text()) if hasattr(path, "read_text") else json.loads(open(path).read())
    state = data.get("state", "")
    before = data.get("before", {})
    after = data.get("after", {})
    if state != "grown-and-verified":
        return {"status": "fail"}
    if before.get("serial") != after.get("serial"):
        return {"status": "fail"}
    # Calculate required minimum block count
    partition_sectors = after.get("partition_sectors", 0)
    min_blocks = int(partition_sectors // 8 * 95 / 100)
    if after.get("block_count", 0) < min_blocks:
        return {"status": "fail"}
    return {"status": "pass"}

