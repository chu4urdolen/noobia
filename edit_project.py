#!/usr/bin/env python3
"""Edit fields of an existing project in the forge database.

Usage:
    python edit_project.py <project_name> [--description TEXT]
    python edit_project.py <project_name> [--hardware 0|1]
"""

import json
import pathlib
import sqlite3
import sys

DB_PATH = pathlib.Path('forge.db')

def main():
    if len(sys.argv) < 3:
        print("Usage: python edit_project.py <project_name> [--description TEXT] [--hardware 0|1]")
        sys.exit(1)
    name = sys.argv[1]
    description = None
    hardware = None
    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == "--description" and i + 1 < len(sys.argv):
            description = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--hardware" and i + 1 < len(sys.argv):
            hardware = int(sys.argv[i + 1])
            i += 2
        else:
            i += 1
    if description is None and hardware is None:
        print("Nothing to update.")
        sys.exit(1)
    with sqlite3.connect(DB_PATH) as con:
        cur = con.execute("SELECT * FROM projects WHERE project_name = ?", (name,))
        if cur.fetchone() is None:
            print(f"Project '{name}' not found.")
            sys.exit(1)
        fields = []
        values = []
        if description is not None:
            fields.append("description = ?")
            values.append(description)
        if hardware is not None:
            fields.append("hardware_ready = ?")
            values.append(hardware)
        values.append(name)
        con.execute(f"UPDATE projects SET {', '.join(fields)} WHERE project_name = ?", values)
        con.commit()
    print(f"Project '{name}' updated.")


if __name__ == "__main__":
    main()
