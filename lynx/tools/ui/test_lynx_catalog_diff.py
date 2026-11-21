"""Offline fixture tests for the source-to-installed catalog diff."""

import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import lynx_catalog_diff as cd  # noqa: E402
import lynx_status_snapshot as snap  # noqa: E402
from test_lynx_status_board import catalog_text  # noqa: E402


def installed():
    return snap.parse_catalog(catalog_text().decode())["files"]


def run(snapshot_text, *argv):
    with TemporaryDirectory() as temp:
        path = Path(temp) / "snap.json"
        path.write_text(snapshot_text)
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cd.main(["--status", str(path), *argv])
    return code, buf.getvalue()


def snapshot_json(files):
    return json.dumps({"captured_at": "2026-11-21T00:00:00Z", "catalog": {"files": files}})


class DiffTest(unittest.TestCase):
    def setUp(self):
        self.source = cd.source_files()

    def test_unchanged_38_of_38(self):
        result = cd.diff(self.source, installed())
        self.assertTrue(result["in_sync"])
        self.assertEqual((result["source_tools"], result["installed_tools"]), (38, 38))
        self.assertEqual(result["counts"]["in_sync"], 38)
        self.assertEqual(result["entries"], [])

    def test_partial_catalog(self):
        files = installed()
        for name in ("lynx_gnss.json", "lynx_gnss.sh", "lynx_codex.sh"):
            files.pop(name)
        files["lynx_camera.json"] = "0" * 64
        result = cd.diff(self.source, files)
        by_tool = {e["tool"]: e for e in result["entries"]}
        self.assertFalse(result["in_sync"])
        self.assertEqual(by_tool["lynx_gnss"]["status"], "missing_on_phone")
        self.assertEqual(by_tool["lynx_codex"]["status"], "partial")
        self.assertEqual(by_tool["lynx_codex"]["files"],
                         {"json": "same", "sh": "missing_on_phone"})
        self.assertEqual(by_tool["lynx_camera"]["status"], "hash_differs")
        self.assertEqual(by_tool["lynx_camera"]["installed_sha256"]["json"], "0" * 12)
        self.assertEqual(result["counts"]["in_sync"], 35)

    def test_added_on_phone(self):
        files = installed()
        files["lynx_extra.json"] = "a" * 64
        files["lynx_extra.sh"] = "b" * 64
        result = cd.diff(self.source, files)
        self.assertEqual(result["entries"][0]["tool"], "lynx_extra")
        self.assertEqual(result["entries"][0]["status"], "added_on_phone")

    def test_hostile_names_are_counted_not_echoed(self):
        files = installed()
        hostile = {"../../etc/passwd": "c" * 64,
                   "<script>alert(1)</script>.json": "d" * 64,
                   "lynx_ok.json": "not-a-hash",
                   "x" * 500 + ".sh": "e" * 64}
        files.update(hostile)
        result = cd.diff(self.source, files)
        self.assertFalse(result["in_sync"])
        self.assertEqual(result["rejected_entries"]["count"], 4)
        dumped = json.dumps(result)
        self.assertNotIn("x" * 41, dumped)
        self.assertNotIn("<script>", json.dumps(result["entries"]))
        self.assertTrue(all(len(p) <= 45 for p in result["rejected_entries"]["preview"]))
        self.assertEqual(result["counts"]["in_sync"], 38)

    def test_duplicate_keys_in_snapshot_are_reported(self):
        files = installed()
        body = snapshot_json(files)
        dup = '"lynx_gnss.sh": "' + "f" * 64 + '", '
        body = body.replace('"lynx_gnss.json"', dup + '"lynx_gnss.json"', 1)
        code, out = run(body)
        result = json.loads(out)
        self.assertEqual(code, 0)
        self.assertFalse(result["in_sync"])
        self.assertEqual(result["duplicate_entries"], ["lynx_gnss.sh"])

    def test_broker_rejects_duplicate_catalog_lines(self):
        text = catalog_text().decode()
        first = text.splitlines()[0]
        with self.assertRaisesRegex(snap.CaptureError, "duplicate"):
            snap.parse_catalog(text + first + "\n")

    def test_output_is_bounded_and_deterministic(self):
        files = {f"lynx_t{i:03d}.json": "a" * 64 for i in range(120)}
        result = cd.diff(self.source, files, limit=10)
        self.assertEqual(len(result["entries"]), 10)
        self.assertEqual(result["entries_truncated"], 120 + 38 - 10)
        code1, out1 = run(snapshot_json(files), "--limit", "10")
        code2, out2 = run(snapshot_json(files), "--limit", "10")
        self.assertEqual(out1, out2)
        code3, text = run(snapshot_json(files), "--limit", "10", "--text")
        self.assertIn("more not shown", text)
        self.assertLess(len(text.splitlines()), 20)


class CommandTest(unittest.TestCase):
    def test_exit_codes(self):
        self.assertEqual(run(snapshot_json(installed()), "--fail-on-drift")[0], 0)
        files = installed()
        files.pop("lynx_gnss.sh")
        self.assertEqual(run(snapshot_json(files))[0], 0)
        self.assertEqual(run(snapshot_json(files), "--fail-on-drift")[0], 2)
        code, out = run(json.dumps({"captured_at": "x"}))
        self.assertEqual(code, 1)
        self.assertIn("no installed catalog", json.loads(out)["error"])
        self.assertEqual(run("not json")[0], 1)

    def test_text_names_exact_tools(self):
        files = installed()
        files.pop("lynx_gnss.sh")
        code, text = run(snapshot_json(files), "--text")
        self.assertIn("DRIFT", text)
        self.assertIn("partial          lynx_gnss  json:same sh:missing_on_phone", text)

    def test_output_never_contains_file_contents(self):
        code, out = run(snapshot_json(installed()))
        for path in (HERE.parent / "local_calls").glob("*.sh"):
            body = path.read_text().strip().splitlines()[-1]
            self.assertNotIn(body, out)


if __name__ == "__main__":
    unittest.main()
