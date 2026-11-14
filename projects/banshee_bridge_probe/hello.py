"""Hello world module for the Banshee Bridge Probe.

This module provides a simple `banner` function that returns a greeting
string.  The accompanying unit test ensures that the function behaves as
expected.
"""

def banner(name: str) -> str:
    """Return a greeting for *name*.

    Parameters
    ----------
    name:
        The name to greet.

    Returns
    -------
    str
        ``"Hello, {name}!"``.
    """
    return f"Hello, {name}!"

