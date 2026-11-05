#!/usr/bin/env python3
"""Line-numbering CLI.

This module implements a small command-line tool that reads from standard input
and writes each line prefixed with its 1‑based line number, a tab, and the
original line text.  The original line endings are preserved, and an empty
input stream produces no output.

The implementation reads the entire input in a memory‑efficient stream
fashion, keeping track of the current line number and writing each line
immediately.  It works correctly even when the last line is not terminated
with a newline.

Usage:
    python3 line_number.py < input.txt > output.txt
"""

import sys


def main() -> None:
    """Read stdin and write numbered lines to stdout.

    The function reads the input line by line using a simple for‑loop over
    ``sys.stdin``.  ``sys.stdin`` iterates over the stream without stripping
    line endings, so the original line endings are preserved in the output.
    """
    line_no = 1
    for line in sys.stdin:
        # ``line`` includes its terminating newline if present.
        sys.stdout.write(f"{line_no}\t{line}")
        line_no += 1


if __name__ == "__main__":
    main()

