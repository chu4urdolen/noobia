"""Tests for common/autonomy/memory/ (NA-60, NA-61, NA-62, NA-63)."""

import tempfile
import unittest
from pathlib import Path

from common.autonomy.memory.journal import JournalManager
from common.autonomy.memory.notes import NotesDB
from common.autonomy.memory.lifestory import LifeStoryManager


class TestMemorySubsystem(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_journal_acknowledged_trim(self):
        j = JournalManager(self.root / "JOURNAL.md")
        j.append_entry("First observation of the day")
        byte_count, digest, _ = j.prepare_collection()

        # Simulate concurrent entry appended while Argus collects
        j.append_entry("Late observation while collecting")

        # Argus acks first slice
        ok = j.acknowledge_and_trim(byte_count, digest)
        self.assertTrue(ok)

        # File must contain the late observation, but not duplicate the first
        content = (self.root / "JOURNAL.md").read_text(encoding="utf-8")
        self.assertIn("Late observation while collecting", content)
        self.assertNotIn("First observation of the day", content)

    def test_notes_fts_search(self):
        db = NotesDB(self.root / "notes.db")
        n1 = db.add_note("Saw a lovely orange cat in the sun", tags="camera,animal")
        n2 = db.add_note("Kernel battery charge completed to 100%", tags="power")

        # Full-text search
        results = db.search("cat")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, n1)

        # Unprocessed notes
        unprocessed = db.get_unprocessed()
        self.assertEqual(len(unprocessed), 2)
        db.mark_processed([n1])
        self.assertEqual(len(db.get_unprocessed()), 1)

    def test_effective_description_builder(self):
        agents_md = self.root / "AGENTS.md"
        agents_md.write_text("# Lynx Role\nBase personality.", encoding="utf-8")
        db = NotesDB(self.root / "notes.db")
        mgr = LifeStoryManager(self.root / "lifestory.json", db, agents_md)

        # Initial prompt
        prompt = mgr.build_effective_description()
        self.assertIn("# Lynx Role", prompt)
        self.assertIn("I am Lynx", prompt)

        # Consolidate day
        mgr.consolidate_day("2026-11-26", "Discovered a new cellular tower and purred at Noob.", yesterday_milestones="Connected to Vivacom")
        updated_prompt = mgr.build_effective_description()
        self.assertIn("Connected to Vivacom", updated_prompt)
        self.assertIn("Discovered a new cellular tower", updated_prompt)


if __name__ == "__main__":
    unittest.main()
