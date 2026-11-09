"""Compatibility shim for legacy tests.

The original repository bundled an :mod:`audit` module under
``projects/lynx_root_audit``.  The unit tests import ``audit`` directly from the
top level.  To keep the test suite working without moving files, this shim
re‑exports :func:`run_audit` from the real implementation.
"""

from projects.lynx_root_audit.audit import run_audit

__all__ = ["run_audit"]

