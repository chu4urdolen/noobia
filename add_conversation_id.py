#!/usr/bin/env python3
"""Add a `conversation_id` column to the projects table and set it for a given project.

The script:
1. Creates the column if it doesn't exist.
2. Generates a UUID4.
3. Updates the specified project with that UUID.
4. Prints the UUID so you can copy it if needed.
"""

import sqlite3
import uuid
from pathlib import Path

DB_PATH = Path("forge.db")

def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # Check if column exists
    cur.execute("PRAGMA table_info(projects)")
    cols = [row[1] for row in cur.fetchall()]
    if "conversation_id" not in cols:
        cur.execute("ALTER TABLE projects ADD COLUMN conversation_id TEXT;")
        conn.commit()
        print("Added conversation_id column")
    else:
        print("conversation_id column already exists")
    # Generate UUID
    conv_id = str(uuid.uuid4())
    print("Generated conversation_id:", conv_id)
    # Update project
    cur.execute(
        "UPDATE projects SET conversation_id = ? WHERE project_name = ?",
        (conv_id, "dushich_foreman"),
    )
    conn.commit()
    print("Updated project with conversation_id")
    conn.close()


if __name__ == "__main__":
    main()
