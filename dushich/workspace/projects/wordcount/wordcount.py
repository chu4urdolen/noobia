#!/usr/bin/env python3
import sys
import json
import argparse
import re
from collections import Counter


def read_words(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        sys.stderr.write(f"Error: file {path} not found\n")
        sys.exit(1)
    # Tokenize alphabetic Unicode words. ``re.findall`` with the pattern
    # ``[^\W\d_]+`` matches sequences of Unicode letters.  ``\W`` matches
    # any non-word character, ``\d`` digits, and ``_`` underscore.  The
    # complement ``[^...]`` therefore yields only letters.  ``re.UNICODE``
    # ensures Unicode character properties are respected.
    words = re.findall(r"[^\W\d_]+", text, flags=re.UNICODE)
    # Use casefold for locale‑independent, aggressive folding.
    words = [w.casefold() for w in words]
    return Counter(words)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Count words in a file")
    parser.add_argument("file", help="path to input file")
    args = parser.parse_args()
    counts = read_words(args.file)
    sorted_counts = dict(sorted(counts.items()))
    print(json.dumps(sorted_counts, ensure_ascii=False))
