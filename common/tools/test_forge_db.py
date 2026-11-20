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
        db.execute("INSERT INTO projects (project_name, executor, receiver, description, hardware_ready, agentic_tools) VALUES ('Rose', 'Aria', 'Rose', 'Rose voice and screen', 0, '[]')")
        db.commit()
        db.close()

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

    def test_tags_curated_attach_filter_and_cleanup(self):
        # Attaching an undefined tag fails; names are normalized to UPPERCASE.
        self.assertEqual(run("tag", "attach", "rose", "--project", "Rose", "--by", "G")[0], 2)
        self.assertEqual(run("tag", "add", "rose", "-d", "Rose's world", "--by", "Dushich")[0], 0)
        self.assertEqual(run("tag", "add", "#net-work", "-d", "Networking", "--by", "Dushich")[0], 0)
        self.assertEqual(run("tag", "add", "x", "-d", "too short", "--by", "D")[0], 2)
        run("path", "set", "/tmp", "-k", "dir", "-d", "scratch", "--tag", "ROSE", "--tag", "NET_WORK", "--by", "G")
        code, out = run("tag", "attach", "ROSE", "--project", "Rose", "--path", "/tmp", "--by", "G")
        self.assertIn("attached to 1 new item", out)  # /tmp already had it
        _, out = run("--json", "path", "get", "/tmp")
        self.assertEqual(json.loads(out)["tag_list"], ["NET_WORK", "ROSE"])
        _, out = run("tag", "list")
        self.assertIn("#ROSE (2)", out)
        _, out = run("search", "--tag", "ROSE", "--tag", "NET_WORK")
        self.assertIn("/tmp", out)
        self.assertNotIn("Project Rose", out)
        _, out = run("project", "get", "Rose")
        self.assertIn("#ROSE", out)
        run("tag", "detach", "ROSE", "--path", "/tmp", "--by", "G")
        run("path", "remove", "/tmp", "--by", "G")
        _, out = run("--json", "stats")
        self.assertEqual(json.loads(out)["tag_links"], 1)
        run("tag", "remove", "ROSE", "--by", "G")
        _, out = run("--json", "stats")
        self.assertEqual((json.loads(out)["tags"], json.loads(out)["tag_links"]), (1, 0))

    def test_check_marks_missing_and_changes_since(self):
        gone = os.path.join(self.folder.name, "gone")
        run("path", "set", gone, "-d", "will vanish", "--by", "Gwyn")
        _, out = run("path", "check", "--prefix", self.folder.name)
        self.assertIn(gone, out)
        _, out = run("--json", "changes", "--since", "2000-01-01")
        self.assertEqual(len(json.loads(out)["paths"]), 1)

    def test_hits_count_only_paths_that_exist(self):
        here, gone = self.folder.name, os.path.join(self.folder.name, "gone")
        run("path", "set", here, "-k", "dir", "-d", "real folder", "--by", "G")
        run("path", "set", gone, "-d", "will vanish", "--by", "G")
        code, out = run("path", "hit", here, "--by", "Dushich")
        self.assertEqual((code, out.strip()), (0, f"hit {here} (hits=1)"))
        run("path", "get", here)  # an exact lookup that finds the path is a hit too
        code, out = run("--json", "path", "hit", gone, "/never/recorded", "--by", "Dushich")
        self.assertEqual(code, 1)
        self.assertEqual([r["hit"] for r in json.loads(out)], [False, False])
        _, out = run("--json", "path", "get", here)
        row = json.loads(out)
        self.assertEqual((row["hit_count"], row["last_hit_by"]), (3, "(path get)"))
        _, out = run("--json", "path", "get", gone)
        self.assertEqual((json.loads(out)["hit_count"], json.loads(out)["present"]), (0, 0))
        _, out = run("path", "list", "--prefix", here, "--sort", "hits")
        self.assertTrue(out.startswith(gone), out)  # least-hit first: retirement candidates
        self.assertIn("hits=3", out)
        # Hits are not edits: they do not appear in `changes`.
        _, out = run("--json", "changes", "--since", "2000-01-01")
        self.assertTrue(all(p["updated_by"] == "G" for p in json.loads(out)["paths"]))

    def test_old_atlas_gains_hit_columns(self):
        db = sqlite3.connect(forge_db.DB)
        db.executescript("DROP TABLE nexus_paths; CREATE TABLE nexus_paths (path TEXT PRIMARY KEY, "
                         "kind TEXT NOT NULL, owner TEXT, description TEXT NOT NULL, tags TEXT NOT NULL "
                         "DEFAULT '', project TEXT, updated_by TEXT NOT NULL, updated_at TEXT NOT NULL, "
                         "present INTEGER, checked_at TEXT);"
                         "INSERT INTO nexus_paths VALUES ('/tmp', 'dir', NULL, 'old row', '', NULL, 'A', 'x', 1, 'x');")
        db.commit()
        db.close()
        _, out = run("--json", "path", "hit", "/tmp", "--by", "G")
        self.assertEqual(json.loads(out)[0]["hits"], 1)

    def test_project_activity_warns_when_two_agents_overlap(self):
        code, out = run("project", "touch", "Rose", "--for", "Banshee", "--by", "Dushich")
        self.assertEqual((code, out.strip()), (0, "Rose: working for Banshee"))
        code, out = run("project", "touch", "Rose", "--for", "Gwyn", "--by", "Dushich")
        self.assertEqual(code, 3)
        self.assertIn("BUSY: Rose is busy: work for Banshee", out)
        _, out = run("--json", "project", "list")
        self.assertEqual(json.loads(out)[0]["modified_for"], "Banshee")  # refused touch records nothing
        code, out = run("project", "touch", "Rose", "--for", "Gwyn", "--together", "--by", "Dushich")
        self.assertEqual(code, 0)
        self.assertIn("before: Banshee", out)
        # A note records work too, and warns instead of failing.
        code, out = run("note", "add", "Rose", "Lights", "--for", "Aria", "--by", "Dushich")
        self.assertEqual(code, 0)
        self.assertIn("WARNING: Rose is busy: work for Gwyn", out)
        _, out = run("project", "get", "Rose")
        self.assertIn("for Aria]", out)
        _, out = run("--json", "changes", "--since", "2000-01-01")
        self.assertEqual(len(json.loads(out)["projects"]), 1)

    def test_old_work_is_not_a_conflict_and_projects_can_be_removed(self):
        db = sqlite3.connect(forge_db.DB)
        db.execute("UPDATE projects SET last_modified='2026-01-01T00:00:00+00:00', modified_for='Aria'")
        db.commit()
        db.close()
        self.assertEqual(run("project", "touch", "Rose", "--for", "Gwyn", "--by", "G")[0], 0)
        run("note", "add", "Rose", "x", "--by", "G")
        self.assertEqual(run("project", "remove", "Rose", "--by", "G")[0], 2)  # has notes
        self.assertEqual(run("project", "remove", "Rose", "--with-notes", "--by", "G")[0], 0)
        _, out = run("--json", "stats")
        self.assertEqual((json.loads(out)["projects"], json.loads(out)["project_notes"]), (0, 0))

    def test_fresh_clone_creates_folder_and_schema(self):
        forge_db.DB = Path(self.folder.name) / "new" / "dushich" / "workspace" / "forge.db"
        code, out = run("--json", "stats")
        self.assertEqual((code, json.loads(out)["projects"]), (0, 0))


if __name__ == "__main__":
    unittest.main()
