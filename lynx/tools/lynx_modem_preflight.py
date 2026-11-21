#!/usr/bin/env python3
"""Forwarding shim for lynx_modem_preflight.py -> lynx/tools/modem/."""
import os
import sys
from pathlib import Path

MODEM_DIR = Path(__file__).resolve().parent / "modem"
sys.path.insert(0, str(MODEM_DIR))
from lynx_modem_preflight import main

if __name__ == "__main__":
    sys.exit(main())
