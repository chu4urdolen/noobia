#!/usr/bin/env python3
import sqlite3
from pathlib import Path

DB_PATH = Path('forge.db')

# create the database and table
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
cur.execute('''
    CREATE TABLE IF NOT EXISTS projects (
        project_name TEXT PRIMARY KEY,
        executor TEXT NOT NULL,
        receiver TEXT NOT NULL,
        description TEXT,
        hardware_ready INTEGER NOT NULL,
        agentic_tools TEXT
    );
''')
conn.commit()
conn.close()
print('Database and table created at', DB_PATH)
