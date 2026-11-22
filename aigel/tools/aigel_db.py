#!/usr/bin/env python3
"""aigel-db: Tool for Aigel (and operators) to inspect, add, edit, and delete pattern DB entries.

Usage:
    aigel-db list [--host lynx] [--ignore 0|1] [--limit 50] [--json]
    aigel-db get <pattern_id> [--json]
    aigel-db add --id <id> --sense <sense> --event <event> [--message <msg>] [--regex <re>] [--ignore 0|1] [--to-noob 0|1] [--p 1] [--host lynx]
    aigel-db edit <pattern_id> [--message <msg>] [--regex <re>] [--ignore 0|1] [--to-noob 0|1] [--p 1]
    aigel-db delete <pattern_id>
    aigel-db test-match "<log_line>" [--host lynx]
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys

_AUTONOMY = Path(__file__).resolve().parents[2] / "common" / "autonomy"
if str(_AUTONOMY) not in sys.path:
    sys.path.insert(0, str(_AUTONOMY))

import sense as _sense
from pattern_db import PatternDB


def cmd_list(db: PatternDB, args: argparse.Namespace) -> int:
    patterns = db.list_patterns(host=args.host)
    if args.ignore is not None:
        target_ignore = bool(int(args.ignore))
        patterns = [p for p in patterns if bool(p.get("is_ignore")) == target_ignore]
    if args.limit:
        patterns = patterns[:args.limit]

    if args.json:
        print(json.dumps(patterns, indent=2))
        return 0

    print(f"Total patterns found: {len(patterns)}")
    print(f"{'PATTERN ID':<30} {'HOST':<8} {'SENSE/EVENT':<25} {'IGN':<4} {'TO_NOOB':<7} {'HITS':<6} {'MESSAGE'}")
    print("-" * 110)
    for p in patterns:
        pid = p.get("pattern_id", "")
        host = p.get("host", "")
        sense_event = f"{p.get('sense', '')}:{p.get('event', '')}"
        ign = "YES" if p.get("is_ignore") else "NO"
        to_noob = "YES" if p.get("to_noob") else "NO"
        hits = str(p.get("count", 0))
        msg = (p.get("output_message") or "")[:35]
        print(f"{pid:<30} {host:<8} {sense_event:<25} {ign:<4} {to_noob:<7} {hits:<6} {msg}")
    return 0


def cmd_get(db: PatternDB, args: argparse.Namespace) -> int:
    p = db.get_pattern(args.pattern_id)
    if not p:
        print(f"Pattern '{args.pattern_id}' not found.", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(p, indent=2))
    else:
        print(f"Pattern ID:   {p.get('id')}")
        print(f"Host:         {p.get('host')}")
        print(f"Match:        {p.get('match')}")
        print(f"Regex:        {p.get('regex') or '(none)'}")
        print(f"Output Msg:   {p.get('message') or '(none)'}")
        print(f"Ignore:       {p.get('ignore')}")
        print(f"To Noob:      {p.get('to_noob')}")
        print(f"Priority:     {p.get('p')}")
        print(f"Hits:         {p.get('hits')}")
        print(f"Added At:     {p.get('added_at')}")
        print(f"Last Hit:     {p.get('last_hit') or 'never'}")
    return 0


def cmd_add(db: PatternDB, args: argparse.Namespace) -> int:
    if args.json_file:
        with open(args.json_file, "r", encoding="utf-8") as f:
            pat_data = json.load(f)
    else:
        if not args.id or not args.sense or not args.event:
            print("Error: --id, --sense, and --event are required to add a pattern.", file=sys.stderr)
            return 2
        is_ign = bool(int(args.ignore)) if args.ignore is not None else False
        to_noob = bool(int(args.to_noob)) if args.to_noob is not None else (not is_ign)
        pat_data = {
            "id": args.id,
            "match": {"sense": args.sense, "event": args.event},
            "regex": args.regex,
            "message": args.message or (None if is_ign else f"Perceived: {args.sense} {args.event}"),
            "ignore": is_ign,
            "to_noob": to_noob,
            "p": args.p or (0 if is_ign else 1),
            "cooldown_s": args.cooldown_s or (0 if is_ign else 300),
            "examples": {
                "must": [args.must] if args.must else [],
                "must_not": [],
            },
        }

    ok = db.upsert_pattern(pat_data, host=args.host or "lynx")
    if ok:
        print(f"Added/Updated pattern '{pat_data.get('id')}' successfully.")
        return 0
    else:
        print("Failed to add pattern.", file=sys.stderr)
        return 1


def cmd_edit(db: PatternDB, args: argparse.Namespace) -> int:
    updates = {}
    if args.message is not None:
        updates["output_message"] = args.message
    if args.regex is not None:
        updates["regex"] = args.regex
    if args.ignore is not None:
        updates["is_ignore"] = 1 if int(args.ignore) else 0
    if args.to_noob is not None:
        updates["to_noob"] = 1 if int(args.to_noob) else 0
    if args.p is not None:
        updates["p"] = int(args.p)
    if args.cooldown_s is not None:
        updates["cooldown_s"] = int(args.cooldown_s)

    if not updates:
        print("No fields specified to edit.", file=sys.stderr)
        return 2

    ok = db.edit_pattern(args.pattern_id, **updates)
    if ok:
        print(f"Updated pattern '{args.pattern_id}' successfully.")
        return 0
    else:
        print(f"Pattern '{args.pattern_id}' not found or update failed.", file=sys.stderr)
        return 1


def cmd_delete(db: PatternDB, args: argparse.Namespace) -> int:
    ok = db.delete_pattern(args.pattern_id)
    if ok:
        print(f"Deleted pattern '{args.pattern_id}'.")
        return 0
    else:
        print(f"Pattern '{args.pattern_id}' not found.", file=sys.stderr)
        return 1


def cmd_test_match(db: PatternDB, args: argparse.Namespace) -> int:
    line = args.line
    patterns = db.get_top_ranker_patterns(args.host, limit=500)
    parsed = _sense.parse_line(line)
    sense_name = parsed.get("sense") if parsed else None
    event_name = parsed.get("event") if parsed else None

    matched = []
    for p in patterns:
        # Check regex
        if p.get("regex"):
            try:
                if re.search(p["regex"], line):
                    matched.append((p, "regex"))
                    continue
            except re.error:
                pass
        # Check structured match
        m = p.get("match", {})
        if sense_name and m.get("sense") == sense_name:
            if not m.get("event") or m.get("event") == event_name:
                text_contains = m.get("text_contains")
                if text_contains and text_contains not in line:
                    continue
                matched.append((p, "structured"))

    if matched:
        print(f"MATCH: {len(matched)} pattern(s) matched line:")
        for p, mode in matched:
            ign = "[IGNORED]" if p.get("ignore") else "[ACTIVE]"
            print(f"  • {p.get('id')} ({mode}) {ign} -> msg: {p.get('message')}")
        return 0
    else:
        print("NO MATCH (Unmatched perception / line).")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="aigel-db: manage pattern DB")
    parser.add_argument("--db-path", default=None, help="Custom database path")
    sub = parser.add_subparsers(dest="action", required=True)

    # list
    p_list = sub.add_parser("list")
    p_list.add_argument("--host", default=None)
    p_list.add_argument("--ignore", choices=["0", "1"], default=None)
    p_list.add_argument("--limit", type=int, default=50)
    p_list.add_argument("--json", action="store_true")

    # get
    p_get = sub.add_parser("get")
    p_get.add_argument("pattern_id")
    p_get.add_argument("--json", action="store_true")

    # add
    p_add = sub.add_parser("add")
    p_add.add_argument("--id")
    p_add.add_argument("--sense")
    p_add.add_argument("--event")
    p_add.add_argument("--message")
    p_add.add_argument("--regex")
    p_add.add_argument("--ignore", choices=["0", "1"])
    p_add.add_argument("--to-noob", choices=["0", "1"])
    p_add.add_argument("--p", type=int)
    p_add.add_argument("--cooldown-s", type=int)
    p_add.add_argument("--must")
    p_add.add_argument("--host", default="lynx")
    p_add.add_argument("--json-file")

    # edit
    p_edit = sub.add_parser("edit")
    p_edit.add_argument("pattern_id")
    p_edit.add_argument("--message")
    p_edit.add_argument("--regex")
    p_edit.add_argument("--ignore", choices=["0", "1"])
    p_edit.add_argument("--to-noob", choices=["0", "1"])
    p_edit.add_argument("--p", type=int)
    p_edit.add_argument("--cooldown-s", type=int)

    # delete
    p_del = sub.add_parser("delete")
    p_del.add_argument("pattern_id")

    # test-match
    p_match = sub.add_parser("test-match")
    p_match.add_argument("line")
    p_match.add_argument("--host", default="lynx")

    args = parser.parse_args()
    db = PatternDB(args.db_path)

    if args.action == "list":
        return cmd_list(db, args)
    elif args.action == "get":
        return cmd_get(db, args)
    elif args.action == "add":
        return cmd_add(db, args)
    elif args.action == "edit":
        return cmd_edit(db, args)
    elif args.action == "delete":
        return cmd_delete(db, args)
    elif args.action == "test-match":
        return cmd_test_match(db, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
