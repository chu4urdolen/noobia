"""Offline tests for dushich-status: synthetic process tables, no /proc or Ollama."""

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import status

CODEX = "/noobia/common/runtime/codex/node_modules/.bin/codex"
MIND = [CODEX, "--oss", "--local-provider", "ollama", "--model", "qwen3.8:27b", "exec", "--json", "-"]
UP = {"up": True, "loaded": True}


def table(*rows):
    """rows: (pid, ppid, start, argv)"""
    return {pid: {"ppid": ppid, "start": start, "argv": argv} for pid, ppid, start, argv in rows}


class JobsTest(unittest.TestCase):
    def test_attribution_and_order(self):
        procs = table(
            (10, 1, 1, ["claude"]), (11, 10, 2, ["python3", "/noobia/common/dushich/mcp.py", "--agent", "gwyn"]),
            (12, 10, 50, ["bash", "-c", "dushich exec ..."]), (13, 12, 51, MIND),
            (20, 1, 3, ["python3", "/noobia/common/dushich/helper_banshee.py", "watch"]), (21, 20, 40, MIND),
            (30, 1, 4, ["python3", "/noobia/common/dushich/bridge.py", "--agent", "banshee", "_worker", "R"]),
            (31, 30, 5, ["bash", "/noobia/dushich/coding/dushich-launcher", "exec"]), (32, 31, 60, MIND),
            (40, 1, 6, ["python3", "/noobia/common/tools/dushich_explore.py", "_worker", "J"]), (41, 40, 70, MIND),
            (50, 1, 7, ["/usr/bin/python3", "/noobia/aria/dushich-bridge", "ask"]), (51, 50, 80, MIND),
            (60, 1, 8, ["python3", "/noobia/common/dushich/helper_mirror.py", "watch"]),
            (61, 60, 90, ["python3", "/noobia/dushich/coding/dushich_summarizer.py", "--file", "x"]),
        )
        found = [(j["pid"], j["agent"], j["kind"]) for j in status.jobs(procs)]
        self.assertEqual(found, [(21, "banshee", "mirror"), (13, "gwyn", "exec"), (32, "banshee", "task"),
                                 (41, "", "explore"), (51, "aria", "ask"), (61, "aria", "mirror")])

    def test_nested_mind_is_one_job_and_interactive_solo_is_ignored(self):
        procs = table(
            (5, 1, 1, ["python3", "/noobia/common/dushich/helper_gwyn.py", "ask"]), (6, 5, 2, MIND),
            (7, 6, 3, ["bash", "-c", "dushich-summarizer --file y"]),
            (8, 7, 4, ["python3", "/noobia/dushich/coding/dushich_summarizer.py", "--file", "y"]),
            (9, 1, 5, [CODEX, "--oss", "--local-provider", "ollama", "--model", "qwen3.8:27b"]),
        )
        self.assertEqual([(j["pid"], j["agent"], j["kind"]) for j in status.jobs(procs)], [(6, "gwyn", "ask")])

    def test_unknown_caller_is_other_and_lone_summarizer_is_summarize(self):
        procs = table((3, 1, 1, ["bash"]), (4, 3, 2, MIND),
                      (6, 3, 3, ["python3", "/noobia/dushich/coding/dushich_summarizer.py"]))
        self.assertEqual([(j["agent"], j["kind"]) for j in status.jobs(procs)], [("", "other"), ("", "summarize")])

    def test_read_processes_reads_this_process(self):
        procs = status.read_processes()
        self.assertIn(os.getpid(), procs)
        self.assertEqual(procs[os.getpid()]["ppid"], os.getppid())


class StateTest(unittest.TestCase):
    live = [{"pid": 1, "agent": "banshee", "kind": "mirror", "start": 1},
            {"pid": 2, "agent": "gwyn", "kind": "task", "start": 2}]

    def test_states(self):
        s = lambda agent, live=self.live, ollama=UP, blocked=False: status.agent_state(agent, live, ollama, blocked)
        self.assertEqual(s("banshee")["text"], "Dushich: reading")
        self.assertEqual(s("gwyn")["text"], "Dushich: queued #2")
        self.assertEqual(s("Aria")["text"], "Dushich: idle · busy")
        self.assertEqual(s("aria", live=[])["text"], "Dushich: idle")
        self.assertEqual(s("aria", live=[], blocked=True)["text"], "Dushich: needs Aria")
        self.assertEqual(s("banshee", ollama={"up": True, "loaded": False})["state"], "loading")
        self.assertEqual(s("gwyn", ollama={"up": False, "loaded": False})["text"], "Dushich: offline")
        self.assertEqual(status.solo_state(self.live, UP)["text"], "Helpers: 2 jobs")
        self.assertEqual(status.solo_state([], UP)["text"], "Helpers: idle")

    def test_every_text_fits_the_sidebar(self):
        texts = [status.agent_state("banshee", [{"pid": 1, "agent": "banshee", "kind": k, "start": 1}], UP, False)["text"]
                 for k in status.LABELS] + ["Dushich: needs Banshee", "Dushich: queued #10", "Helpers: 10 jobs"]
        self.assertLessEqual(max(map(len, texts)), 22, texts)


class BlockedHandoffTest(unittest.TestCase):
    def test_recent_needs_review_only(self):
        with tempfile.TemporaryDirectory() as folder:
            status.NOOBIA = Path(folder)
            runs = Path(folder) / "gwyn-app-nub/private/task-runs"
            now = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
            self.assertFalse(status.blocked_handoff("gwyn", now=now))
            run = runs / "20261126T170000Z-0123abcd"
            run.mkdir(parents=True)
            state = {"status": "needs_gwyn", "finished": (now - timedelta(hours=1)).isoformat()}
            (run / "state.json").write_text(json.dumps(state))
            self.assertTrue(status.blocked_handoff("gwyn", now=now))
            self.assertFalse(status.blocked_handoff("gwyn", now=now + timedelta(hours=12)))
            state["status"] = "done"
            (run / "state.json").write_text(json.dumps(state))
            self.assertFalse(status.blocked_handoff("gwyn", now=now))


if __name__ == "__main__":
    unittest.main()
