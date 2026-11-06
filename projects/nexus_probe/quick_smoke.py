"""A tiny helper module for quick smoke tests.

This file provides a single ``add`` function used in the test suite to
demonstrate the basic workflow of creating a module, writing a test, and
committing the change.  The function simply returns the sum of its two
arguments.

The implementation is intentionally minimal – it is only meant to be a
synthetic example that passes the supplied unittest.
"""

from __future__ import annotations


def add(a, b):
    """Return the arithmetic sum of *a* and *b*.

    Parameters
    ----------
    a, b: int | float
        Numbers to be added.

    Returns
    -------
    int | float
        The result of ``a + b``.
    """
    return a + b

