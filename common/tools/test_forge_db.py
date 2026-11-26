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

    def test_note_archive_copies_up_to_an_id_once(self):
        for text in ("first", "second", "third"):
            self.assertEqual(run("note", "add", "Rose", text, "--by", "Gwyn")[0], 0)
        code, out = run("--json", "note", "archive", "Rose", "--upto", "2", "--by", "Dushich")
        self.assertEqual(code, 0)
        got = json.loads(out)
        self.assertEqual((got["copied"], got["archived_total"], got["last_id"]), (2, 2, 2))
        code, out = run("--json", "note", "archive", "Rose", "--by", "Dushich")   # all; no duplicates
        self.assertEqual(json.loads(out)["copied"], 1)
        self.assertEqual(json.loads(out)["archived_total"], 3)
        code, out = run("--json", "note", "archived", "Rose")
        rows = json.loads(out)
        self.assertEqual([r["note"] for r in rows], ["first", "second", "third"])
        self.assertEqual({r["archived_by"] for r in rows}, {"Dushich"})
        code, out = run("--json", "note", "list", "Rose")                         # a copy, not a move
        self.assertEqual(len(json.loads(out)), 3)
        self.assertEqual(run("note", "archive", "Nope", "--by", "D")[0], 2)

    def test_note_archive_move_leaves_only_newer_notes(self):
        for text in ("old one", "old two", "current state"):
            self.assertEqual(run("note", "add", "Rose", text, "--by", "Gwyn")[0], 0)
        code, out = run("--json", "note", "archive", "Rose", "--upto", "2", "--move", "--by", "Dushich")
        self.assertEqual(code, 0)
        got = json.loads(out)
        self.assertEqual((got["copied"], got["moved"], got["notes_left"]), (2, 2, 1))
        code, out = run("--json", "note", "list", "Rose")
        self.assertEqual([r["note"] for r in json.loads(out)], ["current state"])
        code, out = run("--json", "note", "archived", "Rose")
        self.assertEqual([r["note"] for r in json.loads(out)], ["old one", "old two"])
        code, out = run("--json", "note", "archive", "Rose", "--upto", "2", "--move", "--by", "Dushich")
        self.assertEqual((json.loads(out)["copied"], json.loads(out)["moved"]), (0, 0))   # idempotent

    def test_changes_can_include_moved_archived_notes_once(self):
        for value in ("old", "current"):
            self.assertEqual(run("note", "add", "Rose", value, "--by", "Gwyn")[0], 0)
        self.assertEqual(run("note", "archive", "Rose", "--upto", "1", "--move", "--by", "Dushich")[0], 0)
        _, ordinary = run("--json", "changes", "--since", "2000-01-01")
        self.assertEqual([row["note"] for row in json.loads(ordinary)["notes"]], ["current"])
        _, inclusive = run("--json", "changes", "--since", "2000-01-01", "--include-archived")
        notes = json.loads(inclusive)["notes"]
        self.assertEqual([row["note"] for row in notes], ["old", "current"])
        self.assertEqual([row["id"] for row in notes], [1, 2])
        self.assertNotIn("archived_at", notes[0])

    def test_note_archive_move_never_deletes_a_note_whose_copy_differs(self):
        import sqlite3
        run("note", "add", "Rose", "original", "--by", "Gwyn")
        run("note", "archive", "Rose", "--by", "Dushich")                  # copy only
        con = sqlite3.connect(forge_db.DB)
        con.execute("UPDATE project_notes SET note='edited after copy' WHERE project_name='Rose'")
        con.commit()
        con.close()
        code, out = run("--json", "note", "archive", "Rose", "--move", "--by", "Dushich")
        self.assertEqual(json.loads(out)["moved"], 0)
        code, out = run("--json", "note", "list", "Rose")
        self.assertEqual([r["note"] for r in json.loads(out)], ["edited after copy"])

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


class ForgeDbProjectSetTest(ForgeDbTest):
    """`project set` updates hardware readiness and description."""

    def test_set_updates_hardware_flag_and_description(self):
        code, _ = run("project", "set", "Rose", "--hardware-ready", "--by", "Dushich")
        self.assertEqual(code, 0)
        db = sqlite3.connect(forge_db.DB)
        self.assertEqual(db.execute("SELECT hardware_ready FROM projects").fetchone()[0], 1)
        db.close()
        code, out = run("project", "set", "Rose", "--no-hardware-ready",
                        "--description", "Rose voice, screen, and lights", "--by", "Dushich")
        self.assertEqual(code, 0)
        self.assertIn("Rose voice, screen, and lights", out)
        self.assertIn("hardware not ready", out)

    def test_set_requires_something_to_set_and_known_project(self):
        self.assertEqual(run("project", "set", "Rose", "--by", "D")[0], 2)
        self.assertEqual(run("project", "set", "Nope", "--hardware-ready", "--by", "D")[0], 2)

    def test_spec_set_from_text_and_file_then_read(self):
        code, out = run("project", "spec", "Rose")
        self.assertEqual((code, out.strip()), (0, "Rose has no spec yet"))
        self.assertIn("spec: none yet", run("project", "get", "Rose")[1])
        self.assertEqual(run("project", "set", "Rose", "--spec", "Voice and lights.", "--by", "Dushich")[0], 0)
        code, out = run("project", "spec", "Rose")
        self.assertEqual(code, 0)
        self.assertIn("by Dushich", out)
        self.assertIn("Voice and lights.", out)
        spec_file = Path(self.folder.name) / "spec.md"
        spec_file.write_text("# Rose\nCurrent state: singing.\n", encoding="utf-8")
        self.assertEqual(run("project", "set", "Rose", "--spec-file", str(spec_file), "--by", "Dushich")[0], 0)
        self.assertIn("Current state: singing.", run("project", "spec", "Rose")[1])
        self.assertIn("spec: 30 chars", run("project", "get", "Rose")[1])
        self.assertEqual(run("project", "spec", "Nope")[0], 2)
        self.assertEqual(run("project", "set", "Rose", "--spec-file", "/nonexistent/x", "--by", "D")[0], 2)


class ForgeDbColumnRemovalTest(ForgeDbTest):
    """Older atlases that still carry conversation_id lose it on open."""

    def test_old_atlas_loses_conversation_id(self):
        db = sqlite3.connect(forge_db.DB)
        db.execute("ALTER TABLE projects ADD COLUMN conversation_id TEXT")
        db.execute("UPDATE projects SET conversation_id='019f0000-0000-7000-8000-000000000000'")
        db.commit()
        db.close()
        code, out = run("--json", "project", "get", "Rose")
        self.assertEqual(code, 0)
        self.assertNotIn("conversation_id", out)
        db = sqlite3.connect(forge_db.DB)
        columns = {r[1] for r in db.execute("PRAGMA table_info(projects)")}
        db.close()
        self.assertNotIn("conversation_id", columns)
