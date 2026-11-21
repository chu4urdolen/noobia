"""Offline tests for the status broker and tool board (no phone contacted)."""

from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sys
from contextlib import redirect_stdout
from tempfile import TemporaryDirectory
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import lynx_status_snapshot as snap  # noqa: E402
import lynx_tool_board as board  # noqa: E402
import lynx_tool_manifest as m  # noqa: E402
from test_lynx_tool_manifest import snapshot_from_fixture_tree  # noqa: E402

SOURCE = HERE.parent / "local_calls"
NOW = datetime(2026, 11, 21, 0, 5, tzinfo=timezone.utc)
BOOT = "0fe847d2-44d6-4ac1-9000-2c99df1a51d8"


def catalog_text(source=SOURCE):
    import hashlib
    lines = []
    for path in sorted(source.glob("lynx_*.*")):
        if path.suffix in (".json", ".sh"):
            lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}")
    return ("\n".join(lines) + "\n").encode()


class FakeLynx:
    """Answers the broker's fixed commands from fixture status trees."""

    def __init__(self, root, overrides=None):
        fixture = snapshot_from_fixture_tree(root)
        self.answers = {
            snap.COMMANDS["platform"]: (0, json.dumps(fixture["platform"]).encode(), b""),
            snap.COMMANDS["peripheral"]: (0, json.dumps(fixture["peripheral"]).encode(), b""),
            snap.COMMANDS["hardware"]: (0, json.dumps(fixture["hardware"]).encode(), b""),
            snap.COMMANDS["catalog"]: (0, catalog_text(), b""),
            snap.COMMANDS["boot"]: (0, (BOOT + "\n").encode(), b""),
        }
        for name, answer in (overrides or {}).items():
            self.answers[snap.COMMANDS[name]] = answer
        self.seen = []

    def __call__(self, remote):
        self.seen.append(remote)
        return self.answers[remote]


class BrokerTest(unittest.TestCase):
    def test_runs_only_the_fixed_read_only_commands(self):
        with TemporaryDirectory() as temp:
            fake = FakeLynx(Path(temp))
            result = snap.capture(fake, NOW)
        self.assertEqual(fake.seen, list(snap.COMMANDS.values()))
        for remote in fake.seen:
            self.assertNotRegex(remote, r"(?i)\b(rm|echo|tee|insmod|modprobe|"
                                        r"ccci_mdinit|pulse|play|>)\b|>")
        self.assertEqual(result["errors"], {})
        self.assertEqual(result["captured_at"], "2026-11-21T00:05:00Z")
        self.assertEqual(len(result["catalog"]["files"]), 76)

    def test_full_capture_joins_as_current_and_status_aware(self):
        with TemporaryDirectory() as temp:
            result = snap.capture(FakeLynx(Path(temp)), NOW)
        joined = m.apply_snapshot(m.build(SOURCE), result)
        self.assertEqual(joined["snapshot"]["install_states"], {"current": 38})
        tools = {t["name"]: t for t in joined["tools"]}
        self.assertEqual(tools["lynx_battery_status"]["live"]["state"], "validated")
        self.assertEqual(tools["lynx_haptic_pulse"]["live"]["state"], "interface_only")

    def test_failures_are_recorded_per_source(self):
        with TemporaryDirectory() as temp:
            fake = FakeLynx(Path(temp), {
                "platform": (124, b"", b"local timeout"),
                "peripheral": (0, b"not json", b""),
                "hardware": (0, b"x" * (snap.MAX_OUTPUT + 1), b""),
                "catalog": (0, b"abc  ../../etc/passwd\n", b""),
                "boot": (0, b"not-a-uuid; rm -rf /\n", b""),
            })
            result = snap.capture(fake, NOW)
        self.assertEqual(set(result["errors"]), set(snap.COMMANDS))
        self.assertIn("exit 124", result["errors"]["platform"])
        self.assertIn("not JSON", result["errors"]["peripheral"])
        self.assertIn("exceeds", result["errors"]["hardware"])
        self.assertIn("unexpected catalog line", result["errors"]["catalog"])
        self.assertIn("not a UUID", result["errors"]["boot"])
        for name in snap.COMMANDS:
            self.assertNotIn(name, result)

    def test_changed_and_missing_installs_are_detected(self):
        text = catalog_text().decode().splitlines()
        text = [line for line in text if not line.endswith("lynx_gnss.sh")]
        text = ["0" * 64 + line[64:] if line.endswith("lynx_codex.json") else line
                for line in text]
        text.append("1" * 64 + "  lynx_extra.json")
        with TemporaryDirectory() as temp:
            fake = FakeLynx(Path(temp), {"catalog": (0, "\n".join(text).encode(), b"")})
            joined = m.apply_snapshot(m.build(SOURCE), snap.capture(fake, NOW))
        tools = {t["name"]: t for t in joined["tools"]}
        self.assertEqual(tools["lynx_gnss"]["installed"], "missing")
        self.assertEqual(tools["lynx_codex"]["installed"], "differs")
        self.assertEqual(joined["snapshot"]["installed_not_in_source"], ["lynx_extra"])

    def test_main_writes_atomically_and_reports_partial(self):
        with TemporaryDirectory() as temp:
            out = Path(temp) / "state" / "latest.json"
            fake = FakeLynx(Path(temp), {"hardware": (255, b"", b"ssh: unreachable")})
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = snap.main(["--out", str(out)], runner=fake)
            self.assertEqual(code, 2)
            report = json.loads(buf.getvalue())
            self.assertFalse(report["ok"])
            self.assertIn("unreachable", report["errors"]["hardware"])
            saved = json.loads(out.read_text())
            self.assertIn("platform", saved)
            self.assertEqual(list(out.parent.glob(".snapshot-*")), [])

    def test_nothing_captured_writes_nothing(self):
        with TemporaryDirectory() as temp:
            out = Path(temp) / "latest.json"
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = snap.main(["--out", str(out)],
                                 runner=lambda remote: (255, b"", b"no route"))
            self.assertEqual(code, 1)
            self.assertFalse(out.exists())


class BoardTest(unittest.TestCase):
    def render_with(self, snapshot):
        manifest = m.build(SOURCE)
        if snapshot is not None:
            manifest = m.apply_snapshot(manifest, snapshot)
        return board.render(manifest, NOW)

    def test_board_shows_every_tool_without_scripts_or_controls(self):
        with TemporaryDirectory() as temp:
            captured = snap.capture(FakeLynx(Path(temp)),
                                    datetime(2026, 11, 21, 0, 0, tzinfo=timezone.utc))
            page = self.render_with(captured)
        self.assertEqual(page.count('class="card"'), 38)
        for tag in ("<script", "<form", "<button", "<input", "http://", "https://"):
            self.assertNotIn(tag, page.lower())
        self.assertIn("5 min old", page)
        self.assertIn("battery: proven", page)
        self.assertIn("haptic: present, unproven", page)

    def test_board_without_snapshot_claims_nothing(self):
        page = self.render_with(None)
        self.assertIn("No status snapshot", page)
        self.assertNotIn(">proven<", page)
        self.assertEqual(page.count("badge s-unknown"), 38)

    def test_board_warns_on_errors_and_drift(self):
        with TemporaryDirectory() as temp:
            fake = FakeLynx(Path(temp), {"catalog": (0, b"0" * 64 + b"  lynx_gnss.json\n", b""),
                                         "hardware": (124, b"", b"local timeout")})
            page = self.render_with(snap.capture(fake, NOW))
        self.assertIn("Some sources failed", page)
        self.assertIn("Installed catalog differs from source", page)

    def test_attended_is_shown_apart_from_phone_state(self):
        with TemporaryDirectory() as temp:
            page = self.render_with(snap.capture(FakeLynx(Path(temp)), NOW))
        self.assertIn("haptic: present, unproven", page)
        self.assertIn('<h2 id="attended">Attended confirmations</h2>', page)
        self.assertEqual(page.count('<li class="evidence"'), 5)
        haptic = page.split('data-tool="lynx_haptic_pulse"')[1].split('<li class="card"')[0]
        self.assertIn("s-interface_only", haptic)
        self.assertIn("h-attended", haptic)
        touch = page.split('data-tool="lynx_touch_status"')[1].split('<li class="card"')[0]
        self.assertNotIn("h-attended", touch)
        chips = page.split('<ul class="chips"')[1].split("</ul>")[0]
        self.assertNotIn("attended", chips)

    def test_board_escapes_snapshot_text(self):
        snapshot = {"captured_at": "2026-11-21T00:00:00Z",
                    "hardware": {"gnss": {"interface_ready": True, "validated": False,
                                          "next": "<img src=x onerror=alert(1)>"}}}
        page = self.render_with(snapshot)
        self.assertNotIn("<img", page)
        self.assertIn("&lt;img", page)


if __name__ == "__main__":
    unittest.main()
