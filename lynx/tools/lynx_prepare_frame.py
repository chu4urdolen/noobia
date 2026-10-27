#!/usr/bin/env python3
"""Prepare one 1240×2772 PNG for Lynx's displayctl register command."""

import argparse
import hashlib
from pathlib import Path
import re

from prepare_lynx_pics import encode, FRAMES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("png", type=Path)
    parser.add_argument("--name", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9_]{1,63}", args.name):
        parser.error("name must contain lowercase letters, digits, and underscores")
    if "180deg" in args.name:
        parser.error("the current 180-degree frame is excluded")
    data = encode(args.png)
    FRAMES.mkdir(exist_ok=True)
    target = FRAMES / f"{args.name}.rgb565.gz"
    if target.exists():
        if target.read_bytes() != data:
            parser.error(f"existing frame differs: {target}")
    else:
        target.write_bytes(data)
    print(f"{target} sha256={hashlib.sha256(data).hexdigest()}")


if __name__ == "__main__":
    main()
