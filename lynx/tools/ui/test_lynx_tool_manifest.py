"""Offline tests for the Lynx tool manifest against the source manifests.

Run: python3 -m unittest discover -s lynx/tools/ui -p 'test_*.py'
No test contacts Lynx; status fixtures come from the real inventory functions
run over temporary directory trees.
"""

import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from contextlib import redirect_stdout
from unittest import mock

HERE = Path(__file__).resolve().parent
TOOLS_DIR = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(TOOLS_DIR))

import lynx_tool_manifest as m  # noqa: E402
import lynx_platform_status  # noqa: E402
import lynx_peripheral_status  # noqa: E402
import lynx_hardware  # noqa: E402
N_TOOLS = len(list((Path(__file__).resolve().parents[1] / "local_calls").glob("*.json")))

SOURCE = TOOLS_DIR / "local_calls"
COMMITTED = HERE / "lynx-tool-manifest.json"


def run(argv):
    out = io.StringIO()
    with redirect_stdout(out):
        code = m.main(argv)
    return code, out.getvalue()


def snapshot_from_fixture_tree(root):
    """Build a status snapshot with the phone's own inventory code."""
    health = {
        "battery": {"capacity_percent": 71, "gauge_type": 42495,
                    "read_errors": {"a": 0, "b": 0, "c": 0, "d": 0}},
        "thermal": {"max_mC": 41000},
        "root_filesystem": {"type": "ext4", "source": "/dev/sdc85",
                            "ext4_errors_count": 0},
        "wifi": {"carrier": True, "ipv4": "192.168.100.107"},
    }
    for name in ("sys/module/haptic", "sys/class/leds/vibrator",
                 "sys/module/mediatek_drm", "dev/dri"):
        (root / name).mkdir(parents=True, exist_ok=True)
    (root / "dev/dri/card0").touch()
    return {
        "captured_at": "2026-11-21T00:00:00Z",
        "platform": lynx_platform_status.inventory(root, health),
        "peripheral": lynx_peripheral_status.inventory(root),
        "hardware": lynx_hardware.inventory(root),
    }


class SourceAgreementTest(unittest.TestCase):
    def setUp(self):
        self.manifest = m.build(SOURCE)
        self.by_name = {t["name"]: t for t in self.manifest["tools"]}

    def test_covers_exactly_the_38_source_manifests(self):
        names = sorted(p.stem for p in SOURCE.glob("*.json"))
        self.assertEqual(len(names), N_TOOLS)
        self.assertEqual(sorted(self.by_name), names)
        self.assertEqual(self.manifest["tool_count"], N_TOOLS)

    def test_fields_copied_faithfully_from_each_source(self):
        for path in SOURCE.glob("*.json"):
            spec = json.loads(path.read_text())
            tool = self.by_name[spec["name"]]
            self.assertEqual(tool["description"], spec["description"])
            self.assertEqual(tool["timeout_s"], spec["timeout"])
            self.assertEqual(tool["nrp_id"], spec.get("nrp_id"))
            self.assertEqual(tool["inputs"],
                             sorted(spec["inputSchema"].get("properties", {})))

    def test_status_source_components_match_the_phone_code(self):
        self.assertEqual(m.SOURCES["platform"][1], lynx_platform_status.COMPONENTS)
        self.assertEqual(m.SOURCES["peripheral"][1], lynx_peripheral_status.COMPONENTS)
        self.assertEqual(m.SOURCES["hardware"][1], lynx_hardware.DEVICES)

    def test_every_component_has_a_reporting_tool(self):
        reported = {(t["status_source"], t["component"])
                    for t in self.manifest["tools"] if t["reports_component_status"]}
        for source, (_, parts) in m.SOURCES.items():
            for part in parts:
                self.assertIn((source, part), reported)

    def test_actuating_tools_are_never_read_only(self):
        for name in ("lynx_flashlight_pulse", "lynx_haptic_pulse", "lynx_media_play"):
            self.assertEqual(self.by_name[name]["effect"], "actuates")
        for name in ("lynx_flashlight_stop", "lynx_haptic_stop", "lynx_media_stop"):
            self.assertEqual(self.by_name[name]["effect"], "stops")
        self.assertEqual(self.by_name["lynx_codex"]["effect"], "runs_task")
        for tool in self.manifest["tools"]:
            if tool["effect"] == "read_only":
                for arg in tool["entry"]["args"]:
                    self.assertNotIn(arg, {"pulse", "play", "--duration-ms", "set"},
                                     tool["name"])
        self.assertEqual(self.by_name["lynx_microphone_level"]["effect"],
                         "samples_microphone")

    def test_entry_commands_parsed(self):
        self.assertEqual(self.by_name["lynx_battery_status"]["entry"],
                         {"command": "lynx-platform-status", "args": ["battery"]})
        self.assertEqual(self.by_name["lynx_flashlight_pulse"]["entry"],
                         {"command": "lynx-flashlight-pulse", "args": ["--duration-ms", "100"]})
        self.assertEqual(self.by_name["lynx_agent_health"]["entry"]["command"],
                         "inline-python")

    def test_offline_manifest_claims_no_validation(self):
        text = json.dumps(self.manifest)
        self.assertNotIn('"live"', text)
        self.assertNotIn("snapshot", self.manifest)

    def test_committed_manifest_is_current(self):
        code, out = run(["--source", str(SOURCE), "--check", str(COMMITTED)])
        self.assertEqual(code, 0, out)
        self.assertTrue(json.loads(out)["ok"])


class SourceDriftTest(unittest.TestCase):
    def copy_sources(self, temp):
        target = Path(temp) / "local_calls"
        shutil.copytree(SOURCE, target)
        return target

    def test_new_unclassified_tool_is_rejected(self):
        with TemporaryDirectory() as temp:
            src = self.copy_sources(temp)
            (src / "lynx_new.json").write_text(json.dumps(
                {"name": "lynx_new", "description": "x", "timeout": 5,
                 "inputSchema": {"type": "object", "properties": {}}}))
            (src / "lynx_new.sh").write_text("#!/bin/sh\nexec /usr/local/bin/x\n")
            with self.assertRaisesRegex(m.ManifestError, "unclassified tools"):
                m.build(src)

    def test_missing_wrapper_is_rejected(self):
        with TemporaryDirectory() as temp:
            src = self.copy_sources(temp)
            (src / "lynx_gnss.sh").unlink()
            with self.assertRaisesRegex(m.ManifestError, "pairs differ"):
                m.build(src)

    def test_status_tool_pointing_elsewhere_is_rejected(self):
        with TemporaryDirectory() as temp:
            src = self.copy_sources(temp)
            (src / "lynx_sim_status.sh").write_text(
                "#!/bin/sh\nexec /usr/bin/python3 /usr/local/bin/lynx-platform-status cellular\n")
            with self.assertRaisesRegex(m.ManifestError, "lynx_sim_status"):
                m.build(src)

    def test_changed_source_makes_committed_manifest_stale(self):
        with TemporaryDirectory() as temp:
            src = self.copy_sources(temp)
            spec = json.loads((src / "lynx_gnss.json").read_text())
            spec["timeout"] = 11
            (src / "lynx_gnss.json").write_text(json.dumps(spec))
            code, out = run(["--source", str(src), "--check", str(COMMITTED)])
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(out)["ok"])


class SnapshotTest(unittest.TestCase):
    def manifest_with(self, snapshot):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "status.json"
            path.write_text(json.dumps(snapshot))
            code, out = run(["--source", str(SOURCE), "--status", str(path)])
        self.assertEqual(code, 0, out)
        data = json.loads(out)
        return data, {t["name"]: t for t in data["tools"]}

    def test_fixture_snapshot_from_real_inventory_code(self):
        with TemporaryDirectory() as temp:
            snapshot = snapshot_from_fixture_tree(Path(temp))
        data, tools = self.manifest_with(snapshot)
        live = {name: tool["live"]["state"] for name, tool in tools.items()}
        # validated only where the phone's own status code says so
        self.assertEqual(live["lynx_battery_status"], "validated")
        self.assertEqual(live["lynx_wifi_status"], "validated")
        self.assertEqual(live["lynx_display_status"], "validated")
        # interface present, function unproven
        self.assertEqual(live["lynx_haptic_status"], "interface_only")
        self.assertEqual(live["lynx_haptic_pulse"], "interface_only")
        # absent interfaces
        self.assertEqual(live["lynx_sim_status"], "not_ready")
        self.assertEqual(live["lynx_camera"], "not_ready")
        self.assertEqual(live["lynx_nfc_status"], "not_ready")
        # tools without a status component are never guessed
        self.assertEqual(live["lynx_codex"], "unknown")
        self.assertEqual(live["lynx_platform_status"], "summary")
        self.assertEqual(sum(tools["lynx_platform_status"]["live"]["counts"].values()), 12)
        self.assertEqual(data["snapshot"]["captured_at"], "2026-11-21T00:00:00Z")
        self.assertEqual(sum(data["snapshot"]["component_states"].values()), 20)

    def test_partial_snapshot_leaves_missing_components_unknown(self):
        data, tools = self.manifest_with(
            {"hardware": {"flashlight": {"interface_ready": True, "validated": True,
                                         "next": "use bounded pulse"}}})
        self.assertEqual(tools["lynx_flashlight"]["live"],
                         {"state": "validated", "next": "use bounded pulse"})
        self.assertEqual(tools["lynx_battery_status"]["live"]["state"], "unknown")
        self.assertEqual(tools["lynx_bluetooth"]["live"]["state"], "unknown")

    def test_malformed_entries_are_reported_not_trusted(self):
        _, tools = self.manifest_with(
            {"platform": {"usb": {"interface_ready": "yes", "validated": 1},
                          "touch": "ok"}})
        self.assertEqual(tools["lynx_usb_status"]["live"]["state"], "malformed")
        self.assertEqual(tools["lynx_touch_status"]["live"]["state"], "malformed")

    def test_unusable_snapshots_fail_with_json_error(self):
        with TemporaryDirectory() as temp:
            bad = Path(temp) / "bad.json"
            bad.write_text("[1, 2]")
            code, out = run(["--source", str(SOURCE), "--status", str(bad)])
            self.assertEqual(code, 1)
            self.assertIn("status snapshot", json.loads(out)["error"])
            big = Path(temp) / "big.json"
            big.write_text(" " * (m.MAX_SNAPSHOT_BYTES + 1))
            code, out = run(["--source", str(SOURCE), "--status", str(big)])
            self.assertEqual(code, 1)
            self.assertIn("exceeds", json.loads(out)["error"])

    def test_never_opens_network_or_subprocess(self):
        with TemporaryDirectory() as temp:
            snapshot = snapshot_from_fixture_tree(Path(temp))
            path = Path(temp) / "status.json"
            path.write_text(json.dumps(snapshot))
            boom = mock.Mock(side_effect=AssertionError("live access attempted"))
            with mock.patch("socket.socket", boom), \
                    mock.patch("subprocess.run", boom), \
                    mock.patch("subprocess.Popen", boom):
                code, out = run(["--source", str(SOURCE), "--status", str(path),
                                 "--summary"])
        self.assertEqual(code, 0, out)
        self.assertEqual(len(out.strip().splitlines()), N_TOOLS)


class CleanCheckoutTest(unittest.TestCase):
    """The manifest must be reproducible from files Git actually tracks."""

    def test_every_source_pair_is_tracked_by_git(self):
        try:
            proc = subprocess.run(
                ["git", "-C", str(SOURCE), "ls-files", "--error-unmatch", "--", "."],
                capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.skipTest(f"git unavailable: {exc}")
        if "not a git repository" in proc.stderr:
            self.skipTest("not a Git checkout")
        tracked = {Path(line).name for line in proc.stdout.splitlines()}
        on_disk = {p.name for p in SOURCE.iterdir() if p.suffix in (".json", ".sh")}
        self.assertEqual(sorted(on_disk - tracked), [],
                         "untracked local_calls files break clean-checkout parity")

    def test_receipt_paths_in_repo_exist(self):
        root = TOOLS_DIR.parents[1]
        for entry in m.load_attended():
            for receipt in entry["receipts"]:
                if receipt.startswith("lynx/") and "/logs/" not in receipt:
                    self.assertTrue((root / receipt).is_file(), f"{entry['id']}: {receipt}")


class AttendedEvidenceTest(unittest.TestCase):
    def test_attended_is_listed_per_tool_without_touching_live(self):
        manifest = m.build(SOURCE)
        tools = {t["name"]: t for t in manifest["tools"]}
        self.assertEqual(tools["lynx_haptic_pulse"]["attended"], ["haptic-pulse-2026-11-21"])
        self.assertEqual(tools["lynx_audio_status"]["attended"], ["speaker-beep-2026-11-21"])
        self.assertEqual(tools["lynx_touch_status"]["attended"], [])
        self.assertEqual(tools["lynx_media_catalog"]["attended"], [])
        self.assertEqual(tools["lynx_haptic_stop"]["attended"], [])
        self.assertEqual(tools["lynx_microphone_level"]["attended"], [])
        self.assertEqual(tools["lynx_camera"]["attended"], [])
        self.assertEqual(tools["lynx_platform_status"]["attended"], [])
        snapshot = {"platform": {"haptic": {"interface_ready": True, "validated": False}}}
        joined = {t["name"]: t for t in m.apply_snapshot(manifest, snapshot)["tools"]}
        self.assertEqual(joined["lynx_haptic_pulse"]["live"]["state"], "interface_only")
        self.assertEqual(joined["lynx_haptic_pulse"]["attended"], ["haptic-pulse-2026-11-21"])

    def test_every_entry_states_its_limits(self):
        for entry in m.load_attended():
            self.assertTrue(entry["does_not_establish"])
            self.assertTrue(entry["receipts"])

    def test_bad_attended_files_are_rejected(self):
        good = json.loads(m.ATTENDED_PATH.read_text())["entries"][0]
        cases = {
            "no limits": dict(good, does_not_establish=[]),
            "no receipt": dict(good, receipts=[]),
            "bad component": dict(good, component="platform/teleport"),
            "extra claim field": dict(good, validated=True),
            "no tools": dict(good, tools=[]),
        }
        for label, entry in cases.items():
            with self.subTest(label), TemporaryDirectory() as temp:
                path = Path(temp) / "attended.json"
                path.write_text(json.dumps({"entries": [entry]}))
                with self.assertRaises(m.ManifestError):
                    m.load_attended(path)
        for label, entry in {"unknown tool": dict(good, tools=["lynx_teleport"]),
                             "wrong component": dict(good, tools=["lynx_gnss"])}.items():
            with self.subTest(label), TemporaryDirectory() as temp:
                path = Path(temp) / "attended.json"
                path.write_text(json.dumps({"entries": [entry]}))
                with self.assertRaises(m.ManifestError):
                    m.build(SOURCE, path)
        with TemporaryDirectory() as temp:
            path = Path(temp) / "attended.json"
            path.write_text(json.dumps({"entries": [good, good]}))
            with self.assertRaisesRegex(m.ManifestError, "repeated"):
                m.load_attended(path)


if __name__ == "__main__":
    unittest.main()
