#!/usr/bin/env python3
"""Add a tool name to a project's agentic_tools list.

Usage:
    python add_project_tool.py <project_name> <tool_name>
"""

import json
import pathlib
import sqlite3
import sys

DB_PATH = pathlib.Path('forge.db')

def main():
    if len(sys.argv) != 3:
        print("Usage: python add_project_tool.py <project_name> <tool_name>")
        sys.exit(1)
    name = sys.argv[1]
    tool = sys.argv[2]
    with sqlite3.connect(DB_PATH) as con:
        cur = con.execute("SELECT agentic_tools FROM projects WHERE project_name = ?", (name,))
        row = cur.fetchone()
        if not row:
            print(f"Project '{name}' not found.")
            sys.exit(1)
        tools = json.loads(row[0]) if row[0] else []
        if tool in tools:
            print(f"Tool '{tool}' already present.")
            sys.exit(0)
        tools.append(tool)
        con.execute("UPDATE projects SET agentic_tools = ? WHERE project_name = ?", (json.dumps(tools), name))
        con.commit()
    print(f"Added tool '{tool}' to project '{name}'.")


if __name__ == "__main__":
    main()
