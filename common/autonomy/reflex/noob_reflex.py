#!/usr/bin/env python3
"""CLI for Managing Deterministic Reflexes on Lynx (NA-41)."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, "/noobia")
from common.autonomy.reflex.engine import ReflexEngine

DEFAULT_DB = "/var/lib/noobia/reflex/reflexes.db"


def main():
    parser = argparse.ArgumentParser(description="Noob Reflex Manager")
    parser.add_argument("--db", default=DEFAULT_DB, help="Path to reflex database")
    sub = parser.add_subparsers(dest="command", required=True)

    # list
    sub.add_parser("list", help="List active reflexes")

    # add
    p_add = sub.add_parser("add", help="Add new reflex")
    p_add.add_argument("pattern", help="Regex pattern matching sense event")
    p_add.add_argument("script", help="Path to executable script")
    p_add.add_argument("--author", default="lynx-coder")
    p_add.add_argument("--desc", default="")

    # enable/disable
    p_en = sub.add_parser("enable", help="Enable reflex by ID")
    p_en.add_argument("id", type=int)

    p_dis = sub.add_parser("disable", help="Disable reflex by ID")
    p_dis.add_argument("id", type=int)

    args = parser.parse_args()
    engine = ReflexEngine(args.db)

    if args.command == "list":
        rules = engine.list_rules(enabled_only=False)
        print(f"ID | Enabled | Pattern | Script | Description")
        print("-" * 60)
        for r in rules:
            status = "YES" if r.enabled else "NO"
            print(f"{r.id:<2} | {status:<7} | {r.pattern:<15} | {r.script_path} | {r.description}")
    elif args.command == "add":
        rid = engine.add_rule(args.pattern, args.script, author=args.author, description=args.desc)
        print(f"Created reflex ID {rid}")
    elif args.command == "enable":
        ok = engine.set_enabled(args.id, True)
        print(f"Reflex {args.id} enabled: {ok}")
    elif args.command == "disable":
        ok = engine.set_enabled(args.id, False)
        print(f"Reflex {args.id} disabled: {ok}")


if __name__ == "__main__":
    main()
