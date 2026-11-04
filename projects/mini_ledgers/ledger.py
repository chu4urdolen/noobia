#!/usr/bin/env python3
"""A small CLI to sum amounts per name from a CSV.

Usage:
    python -m projects.mini_ledgers.ledger <csv_file>

The CSV must have two columns: name,amount. Amounts are parsed as Decimal.
The script outputs a JSON object mapping names to their total Decimal string
representation. Errors are printed to stderr and exit with status 1.
"""

import sys
import csv
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

__all__ = ["main"]


def read_csv(path: Path):
    totals = {}
    with path.open(newline='') as f:
        reader = csv.reader(f)
        for lineno, row in enumerate(reader, start=1):
            if not row:
                continue  # skip empty lines
            if len(row) != 2:
                raise ValueError(f"Line {lineno}: expected 2 columns, got {len(row)}")
            name, amount_str = row
            name = name.strip()
            amount_str = amount_str.strip()
            if not name:
                raise ValueError(f"Line {lineno}: empty name")
            try:
                amount = Decimal(amount_str)
            except InvalidOperation as exc:
                raise ValueError(f"Line {lineno}: invalid amount '{amount_str}'") from exc
            # Reject non‑finite Decimal values such as NaN or Infinity
            if not amount.is_finite():
                raise ValueError(f"Line {lineno}: non‑finite amount '{amount_str}'")
            totals[name] = totals.get(name, Decimal('0')) + amount
    return totals


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if len(argv) != 1:
        print("Usage: python -m projects.mini_ledgers.ledger <csv_file>", file=sys.stderr)
        sys.exit(1)
    csv_path = Path(argv[0])
    if not csv_path.is_file():
        print(f"Error: file '{csv_path}' not found", file=sys.stderr)
        sys.exit(1)
    try:
        totals = read_csv(csv_path)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    # Convert Decimals to strings for JSON serialization
    json_obj = {k: str(v) for k, v in totals.items()}
    print(json.dumps(json_obj, sort_keys=True))

if __name__ == "__main__":
    main()
