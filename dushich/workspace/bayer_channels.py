"""Compatibility shim for :mod:`projects.lynx_gain.bayer_channels`.

The original test suite imports ``bggr_channel_stats`` from a top‑level
``bayer_channels`` module.  In this repository the implementation lives in
``projects/lynx_gain/bayer_channels.py``.  To keep the test unchanged we
provide this thin wrapper that re‑exports the function.
"""

from projects.lynx_gain.bayer_channels import bggr_channel_stats  # noqa: F401

__all__ = ["bggr_channel_stats"]

