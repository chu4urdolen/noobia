#!/usr/bin/env python3
"""Control Lynx's display over her existing pinned Alpine SSH connection."""

import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import sys

from lynx_wifi_v19_contact import ssh_command


IP = "192.168.100.107"
NAME = re.compile(r"[a-z0-9_]{1,63}\Z")


def run(command, payload=None, timeout=25):
    argv = ssh_command(IP, command)
    argv[-2:-2] = ["-p", "2222"]
    result = subprocess.run(argv, input=payload, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace").strip() or
                           f"SSH command failed ({result.returncode})")
    return result.stdout.decode(errors="replace").strip()


def valid(name):
    if not NAME.fullmatch(name):
        raise ValueError("invalid pose or animation name")
    return name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("list", "status"):
        sub.add_parser(command)
    for command in ("pose", "animate"):
        sub.add_parser(command).add_argument("name")
    define = sub.add_parser("define-animation")
    define.add_argument("name")
    define.add_argument("frames", nargs="+")
    register = sub.add_parser("register")
    register.add_argument("name")
    register.add_argument("frame", type=Path,
                          help="RGB565 gzip frame made by lynx_prepare_frame.py")
    args = parser.parse_args()
    if args.command in ("list", "status"):
        print(run(f"/usr/local/bin/lynx-displayctl {args.command}"))
    elif args.command in ("pose", "animate"):
        print(run(f"/usr/local/bin/lynx-displayctl {args.command} {valid(args.name)}"))
    elif args.command == "define-animation":
        words = [valid(args.name), *(valid(frame) for frame in args.frames)]
        print(run("/usr/local/bin/lynx-displayctl define-animation " + " ".join(words)))
    elif args.command == "register":
        name = valid(args.name)
        data = args.frame.read_bytes()
        if len(data) > 8 * 1024 * 1024 or not data.startswith(b"\x1f\x8b"):
            raise ValueError("frame must be a gzip file of at most 8 MiB")
        inbox = f"/var/lib/lynx-display/inbox/{name}.rgb565.gz"
        digest = hashlib.sha256(data).hexdigest()
        run(f"set -eu; mkdir -p /var/lib/lynx-display/inbox; test ! -e {inbox}; "
            f"cat > {inbox}", data, timeout=55)
        try:
            run(f"set -eu; test \"$(sha256sum {inbox} | cut -c1-64)\" = {digest}; "
                f"/usr/local/bin/lynx-displayctl register {name} {inbox}", timeout=40)
        finally:
            run(f"rm -f {inbox}")
        print(f"registered {name}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"lynx-display-remote: {exc}", file=sys.stderr)
        raise SystemExit(1)
