"""Migration probe package.

This package contains a small helper that doubles an integer. It is
intentionally trivial but serves as a target for unit tests.
"""

def double(x: int) -> int:
    """Return the integer ``x`` multiplied by two.

    Parameters
    ----------
    x:
        Any integer.  The function accepts negative values, zero, and
        positive values.
    """
    return x * 2

