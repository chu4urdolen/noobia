#!/usr/bin/env python3
"""lynx_reflex: Agent tool for Lynx to inspect and create autonomous reflexes (NA-42)."""

import json
import os
from pathlib import Path
import stat
import sys

HERE = Path(__file__).resolve().parent
for p in ("/usr/local/lib/noobia/autonomy", "/usr/local/lib/noobia/autonomy/reflex",
          "/noobia/common/autonomy", "/noobia/common/autonomy/reflex"):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from engine import ReflexEngine
except ImportError:
    from common.autonomy.reflex.engine import ReflexEngine

DB_PATH = Path(os.environ.get("NOOBIA_REFLEX_DB", "/var/lib/noobia/reflex/reflexes.db"))
SCRIPTS_DIR = Path(os.environ.get("NOOBIA_REFLEX_SCRIPTS", "/var/lib/noobia/reflex/scripts"))


def main():
    try:
        raw = sys.stdin.read(4096)
        args = json.loads(raw or "{}") if raw else {}
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": f"Invalid JSON payload: {exc}"}))
        return 1

    action = args.get("action", "list").lower()
    engine = ReflexEngine(DB_PATH, noob_name="lynx")

    if action == "list":
        rules = engine.list_rules(enabled_only=False)
        print(json.dumps({
            "ok": True,
            "reflexes": [
                {
                    "id": r.id,
                    "pattern": r.pattern,
                    "script_path": r.script_path,
                    "enabled": r.enabled,
                    "author": r.author,
                    "version": r.version,
                    "description": r.description
                }
                for r in rules
            ]
        }))
        return 0

    elif action == "add":
        pattern = args.get("pattern")
        command = args.get("command") or args.get("script")
        desc = args.get("description", "")
        if not pattern or not command:
            print(json.dumps({"ok": False, "error": "Missing required fields: pattern and command"}))
            return 1

        SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
        if command.startswith("/") and Path(command.split()[0]).is_file():
            script_path = command
        else:
            # Generate a wrapper script
            script_name = f"reflex_{int(os.time() if hasattr(os, 'time') else 0)}_{os.getpid()}.sh"
            script_file = SCRIPTS_DIR / script_name
            with open(script_file, "w", encoding="utf-8") as f:
                f.write(f"#!/bin/sh\n# Reflex script created by Lynx\nexec {command}\n")
            script_file.chmod(0o755)
            script_path = str(script_file)

        rule_id = engine.add_rule(pattern, script_path, author="lynx", description=desc)
        print(json.dumps({
            "ok": True,
            "id": rule_id,
            "pattern": pattern,
            "script_path": script_path,
            "message": f"Autonomous reflex {rule_id} added successfully."
        }))
        return 0

    elif action in ("enable", "disable"):
        rule_id = args.get("id") or args.get("reflex_id")
        if rule_id is None:
            print(json.dumps({"ok": False, "error": "Missing reflex ID"}))
            return 1
        success = engine.set_enabled(int(rule_id), action == "enable")
        print(json.dumps({"ok": success, "id": int(rule_id), "enabled": (action == "enable")}))
        return 0 if success else 1

    elif action == "test":
        event_line = args.get("event") or args.get("test_event", "")
        if not event_line:
            print(json.dumps({"ok": False, "error": "Missing event string to test"}))
            return 1
        rules = engine.list_rules(enabled_only=True)
        import re
        matches = [
            {"id": r.id, "pattern": r.pattern, "script": r.script_path}
            for r in rules if re.search(r.pattern, event_line)
        ]
        print(json.dumps({"ok": True, "event": event_line, "matches": matches}))
        return 0

    print(json.dumps({"ok": False, "error": f"Unknown action: {action}"}))
    return 1


if __name__ == "__main__":
    sys.exit(main())
