#!/usr/bin/env python3
"""Compatibility shim (2026-11-20): the bridge moved to common/dushich/bridge.py.

Sessions started before the move still call this path. Remove it once every
banshee session has been restarted.
"""
import os
import sys

os.execv(sys.executable, [sys.executable, os.path.join(os.environ.get("NOOBIA", "/noobia"),
         "common/dushich/bridge.py"), "--agent", "banshee", *sys.argv[1:]])
