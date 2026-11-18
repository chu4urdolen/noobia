import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import forge_db


def run(*argv):
    out = StringIO()
    with redirect_stdout(out):
        code = forge_db.main(list(argv))
    return code, out.getvalue()


class ForgeDbTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        forge_db.DB = Path(self.folder.name) / "forge.db"
        forge_db._model = forge_db._gpu = False  # keyword search only in tests
        db = sqlite3.connect(forge_db.DB)
        db.executescript(forge_db.SCHEMA)
        db.execute("INSERT INTO projects VALUES ('Rose', 'Aria', 'Rose', 'Rose voice and screen', 0, '[]', NULL)")
        db.commit()

    def tearDown(self):
        self.folder.cleanup()

    def test_path_roundtrip_and_search(self):
        code, _ = run("path", "set", self.folder.name, "-k", "dir", "-o", "Gwyn",
                      "-d", "Scratch atlas folder", "-t", "temp", "--project", "Rose", "--by", "Gwyn")
        self.assertEqual(code, 0)
        code, out = run("--json", "path", "get", self.folder.name)
        row = json.loads(out)
        self.assertEqual((row["kind"], row["present"], row["project"]), ("dir", 1, "Rose"))
        code, out = run("search", "atlas", "scratch")
        self.assertIn(self.folder.name, out)
        code, out = run("project", "get", "Rose")
        self.assertIn("Scratch atlas folder", out)

    def test_update_keeps_tags_when_omitted(self):
        run("path", "set", "/tmp", "-k", "dir", "-d", "first", "-t", "keep", "--by", "A")
        run("path", "set", "/tmp", "-k", "dir", "-d", "second", "--by", "B")
        _, out = run("--json", "path", "get", "/tmp")
        row = json.loads(out)
        self.assertEqual((row["description"], row["tags"], row["updated_by"]), ("second", "keep", "B"))

    def test_notes_require_known_project_and_absolute_paths(self):
        self.assertEqual(run("note", "add", "Nope", "x", "--by", "D")[0], 2)
        self.assertEqual(run("note", "add", "Rose", "x", "--path", "relative", "--by", "D")[0], 2)
        code, _ = run("note", "add", "Rose", "Beat grid ready", "--path", "/tmp", "--by", "Dushich")
        self.assertEqual(code, 0)
        _, out = run("note", "list", "Rose")
        self.assertIn("Dushich: Beat grid ready", out)

    def test_check_marks_missing_and_changes_since(self):
        gone = os.path.join(self.folder.name, "gone")
        run("path", "set", gone, "-d", "will vanish", "--by", "Gwyn")
        _, out = run("path", "check", "--prefix", self.folder.name)
        self.assertIn(gone, out)
        _, out = run("--json", "changes", "--since", "2000-01-01")
        self.assertEqual(len(json.loads(out)["paths"]), 1)


if __name__ == "__main__":
    unittest.main()
