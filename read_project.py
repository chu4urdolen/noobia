#!/usr/bin/env python3
"""Read a project from the forge database.

Usage:
    python read_project.py <project_name_or_conversation_id>
"""

import json
import pathlib
import sqlite3
import sys

DB_PATH = pathlib.Path('forge.db')

def main():
    if len(sys.argv) != 2:
        print("Usage: python read_project.py <project_name_or_conversation_id>")
        sys.exit(1)
    name = sys.argv[1]
    with sqlite3.connect(DB_PATH) as con:
        cur = con.execute(
            "SELECT project_name, executor, receiver, description, hardware_ready, agentic_tools, conversation_id FROM projects WHERE project_name = ? OR conversation_id = ? ORDER BY CASE WHEN project_name = ? THEN 0 ELSE 1 END LIMIT 1",
            (name, name, name),
        )
        row = cur.fetchone()
        if not row:
            print(f"Project '{name}' not found.")
            sys.exit(1)
        data = {
            "project_name": row[0],
            "executor": row[1],
            "receiver": row[2],
            "description": row[3],
            "hardware_ready": bool(row[4]),
            "agentic_tools": json.loads(row[5]) if row[5] else [],
            "conversation_id": row[6],
        }
        print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
