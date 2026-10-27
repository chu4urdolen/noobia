#!/usr/bin/env python3
"""Run Lynx's local media controller through pinned Alpine SSH."""

import argparse
import re
import subprocess
import sys

from lynx_wifi_v19_contact import ssh_command

NAME = re.compile(r"[a-z0-9_]{1,63}\Z")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["catalog", "status", "play", "pause",
                                          "resume", "stop", "queue", "next",
                                          "previous", "clear"])
    parser.add_argument("kind", nargs="?", choices=["sound", "image"])
    parser.add_argument("item", nargs="?")
    args = parser.parse_args()
    if args.action not in ("catalog", "status") and args.kind is None:
        parser.error("a kind is required")
    if args.action in ("play", "queue") and (
            args.item is None or not NAME.fullmatch(args.item)):
        parser.error("a catalog item name is required")
    if args.item and not NAME.fullmatch(args.item):
        parser.error("invalid item name")
    command = " ".join(["/usr/local/bin/lynx-media", args.action,
                        *([args.kind] if args.kind else []),
                        *([args.item] if args.item else [])])
    argv = ssh_command("192.168.100.107", command)
    argv[-2:-2] = ["-p", "2222"]
    result = subprocess.run(argv, capture_output=True, timeout=15)
    sys.stdout.buffer.write(result.stdout)
    sys.stderr.buffer.write(result.stderr)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
