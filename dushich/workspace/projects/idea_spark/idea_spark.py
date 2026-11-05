"""A tiny CLI that generates a Noobian invention prompt.

Usage:
    python3 projects/idea_spark/idea_spark.py --seed 7

The program picks a subject, an action and a constraint from short built‑in
lists using ``random.Random(seed).choice``.  The output is a single English
sentence that describes a new invention.  The seed guarantees deterministic
output for a given integer.  The script is intentionally small (<45 lines)
and relies only on the standard library.
"""

from __future__ import annotations

import argparse
import random
import sys

SUBJECTS = [
    "light", "sound", "gravity", "time", "space", "matter", "energy",
    "color", "text", "memory", "vision", "touch", "scent", "taste",
]
ACTIONS = [
    "compress", "magnify", "split", "merge", "convert", "store", "transmit",
    "transform", "observe", "predict", "animate", "illuminate", "erase",
]
CONSTRAINTS = [
    "without power", "using only solar energy", "in a vacuum", "in microgravity",
    "within a single atom", "at the speed of light", "without moving parts",
]


def generate_prompt(seed: int) -> str:
    rng = random.Random(seed)
    subject = rng.choice(SUBJECTS)
    action = rng.choice(ACTIONS)
    constraint = rng.choice(CONSTRAINTS)
    # Use a clearer template that encourages actionability.
    return f"Build a device that can {action} {subject} {constraint}."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a Noobian invention prompt.")
    parser.add_argument("--seed", type=int, required=True, help="Random seed for deterministic output")
    args = parser.parse_args(argv)
    prompt = generate_prompt(args.seed)
    print(prompt)
    return 0


if __name__ == "__main__":
    sys.exit(main())

