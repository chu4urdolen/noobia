#!/usr/bin/env python3
"""
seekline – a simple line‑search utility.
"""

import argparse
import json
import re
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Search UTF‑8 text files for a regex pattern."
    )
    parser.add_argument("pattern", help="Regex pattern to search for")
    parser.add_argument("files", nargs="+", help="Files to search")
    parser.add_argument(
        "--ignore-case",
        action="store_true",
        help="Perform a case‑insensitive search",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as a JSON array",
    )
    args = parser.parse_args()

    if args.pattern == "":
        sys.stderr.write("Error: Pattern cannot be empty.\n")
        sys.exit(1)

    flags = re.IGNORECASE if args.ignore_case else 0
    try:
        regex = re.compile(args.pattern, flags)
    except re.error as exc:
        sys.stderr.write(f"Error: invalid regex pattern: {exc}\n")
        sys.exit(1)

    results = []
    for path in args.files:
        try:
            with open(path, "r", encoding="utf-8") as fp:
                for line_no, line in enumerate(fp, start=1):
                    if regex.search(line):
                        # Preserve the line text except for the line ending.
                        # ``rstrip("\r\n")`` removes only CR and LF characters,
                        # leaving any trailing spaces intact.  This is important
                        # for both plain‑text and JSON output so that the
                        # original file content is represented exactly.
                        cleaned = line.rstrip("\r\n")
                        if args.json:
                            results.append(
                                {
                                    "path": path,
                                    "line_number": line_no,
                                    "text": cleaned,
                                }
                            )
                        else:
                            sys.stdout.write(
                                f"{path}:{line_no}:{cleaned}\n"
                            )
        except FileNotFoundError as exc:
            sys.stderr.write(f"Error: cannot open file {path}: {exc}\n")
            sys.exit(1)

    if args.json:
        json.dump(results, sys.stdout)
        sys.stdout.write("\n")

    sys.exit(0)


if __name__ == "__main__":
    main()

