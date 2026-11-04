#!/usr/bin/env python3
import sys
import json
import argparse
from collections import Counter


def read_words(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        sys.stderr.write(f"Error: file {path} not found\n")
        sys.exit(1)
    words = text.split()
    words = [w.lower() for w in words]
    return Counter(words)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Count words in a file")
    parser.add_argument("file", help="path to input file")
    args = parser.parse_args()
    counts = read_words(args.file)
    sorted_counts = dict(sorted(counts.items()))
    print(json.dumps(sorted_counts, ensure_ascii=False))
