"""Offline fixture tests for the Lynx tool coverage audit (never contacts Lynx)."""

import copy
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import lynx_tool_coverage as cov  # noqa: E402
import lynx_tool_manifest as mm  # noqa: E402
from test_lynx_status_board import FakeLynx, NOW  # noqa: E402
import lynx_status_snapshot as snap  # noqa: E402

SOURCE = HERE.parent / "local_calls"


def fixture_snapshot():
    with TemporaryDirectory() as temp:
        return snap.capture(FakeLynx(Path(temp)), NOW)


def live_like_snapshot():
    """Fixture shaped like the 2026-11-21 live snapshot's key states."""
    data = fixture_snapshot()
    hw = data["hardware"]
    hw["flashlight"].update(interface_ready=False, validated=False)
    hw["flashlight"]["evidence"].update(driver_bound=False,
                                        visual_confirmation_recorded=True)
    hw["camera"]["evidence"]["driver_loaded"] = False
    hw["bluetooth"].update(interface_ready=True, validated=False)
    hw["bluetooth"]["evidence"].update(driver_loaded=True,
                                       hci_exchange_trial_verified=True)
    data["platform"]["haptic"].update(interface_ready=True, validated=False)
    return data


class CoverageTest(unittest.TestCase):
    def setUp(self):
        self.manifest = mm.build(SOURCE)

    def test_every_component_and_tool_is_accounted_for(self):
        report = cov.audit(self.manifest)
        self.assertEqual(len(report["components"]), 21)  # 20 + agent/*
        listed = set()
        for entry in report["components"].values():
            for key in ("status_tools", "read_tools", "action_tools", "stop_tools"):
                listed.update(entry[key])
        aggregates = {"lynx_platform_status", "lynx_peripheral_status"}
        self.assertEqual(listed | aggregates, {t["name"] for t in self.manifest["tools"]})
        self.assertEqual(report["gaps"]["components_without_tools"], [])

    def test_component_with_no_tool_is_reported(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["tools"] = [t for t in manifest["tools"] if t["component"] != "gnss"]
        report = cov.audit(manifest, live_like_snapshot())
        self.assertIn("hardware/gnss", report["gaps"]["components_without_tools"])
        gnss = [n for n in report["gaps"]["not_ready"] if n["component"] == "hardware/gnss"]
        self.assertEqual(gnss[0]["cause"], "no_tool_source")

    def test_action_companions(self):
        report = cov.audit(self.manifest)
        by_tool = {c["tool"]: c for c in report["action_companions"]}
        self.assertEqual(set(by_tool), {"lynx_media_play", "lynx_haptic_pulse",
                                        "lynx_flashlight_pulse", "lynx_codex"})
        self.assertEqual(by_tool["lynx_haptic_pulse"]["missing"], [])
        self.assertEqual(by_tool["lynx_flashlight_pulse"]["stop_tools"],
                         ["lynx_flashlight_stop"])
        self.assertEqual(by_tool["lynx_codex"]["missing"], ["stop"])
        self.assertEqual([c["tool"] for c in report["gaps"]["actions_missing_companions"]],
                         ["lynx_codex"])

    def test_removing_a_stop_tool_is_flagged(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["tools"] = [t for t in manifest["tools"] if t["name"] != "lynx_haptic_stop"]
        report = cov.audit(manifest)
        flagged = {c["tool"]: c["missing"] for c in report["gaps"]["actions_missing_companions"]}
        self.assertEqual(flagged["lynx_haptic_pulse"], ["stop"])

    def test_source_only_audit_claims_no_state(self):
        report = cov.audit(self.manifest)
        gaps = report["gaps"]
        self.assertIsNone(report["snapshot"])
        self.assertEqual(gaps["unverified"], [])
        self.assertEqual(gaps["not_ready"], [])
        self.assertEqual(len(gaps["phone_state_unknown"]), 20)
        self.assertEqual(gaps["catalog_drift"], {"checked": False})

    def test_unloaded_driver_vs_absent_interface_vs_prior_success(self):
        report = cov.audit(self.manifest, live_like_snapshot())
        causes = {n["component"]: n for n in report["gaps"]["not_ready"]}
        flash = causes["hardware/flashlight"]
        self.assertEqual(flash["cause"], "driver_not_loaded")
        self.assertEqual(flash["driver_flags"], {"driver_bound": False})
        self.assertEqual(flash["prior_success_flags"], ["visual_confirmation_recorded"])
        self.assertEqual(flash["attended"], ["rear-led-pulse-2026-11-02"])
        self.assertEqual(causes["hardware/camera"]["cause"], "driver_not_loaded")
        self.assertEqual(causes["hardware/camera"]["prior_success_flags"], [])
        self.assertEqual(causes["platform/sim"]["cause"], "interface_absent")

    def test_missing_install_is_its_own_cause(self):
        data = live_like_snapshot()
        data["catalog"]["files"].pop("lynx_camera.sh")
        report = cov.audit(self.manifest, data)
        causes = {n["component"]: n["cause"] for n in report["gaps"]["not_ready"]}
        self.assertEqual(causes["hardware/camera"], "tool_not_installed")
        self.assertEqual(report["gaps"]["catalog_drift"]["missing"], ["lynx_camera"])

    def test_attended_never_counts_as_phone_validation(self):
        report = cov.audit(self.manifest, live_like_snapshot())
        haptic = report["components"]["platform/haptic"]
        self.assertEqual(haptic["phone_state"], "interface_only")
        self.assertEqual(haptic["attended"], ["haptic-pulse-2026-11-21"])
        unverified = {u["component"]: u for u in report["gaps"]["unverified"]}
        self.assertIn("platform/haptic", unverified)
        self.assertEqual(unverified["platform/haptic"]["attended"],
                         ["haptic-pulse-2026-11-21"])
        bt = unverified["hardware/bluetooth"]
        self.assertEqual(bt["prior_success_flags"], ["hci_exchange_trial_verified",
                                                  "nexus_le_connection_trial_verified"])

    def test_catalog_drift(self):
        data = live_like_snapshot()
        files = data["catalog"]["files"]
        files["lynx_gnss.json"] = "0" * 64
        files["lynx_rogue.sh"] = "1" * 64
        drift = cov.audit(self.manifest, data)["gaps"]["catalog_drift"]
        self.assertTrue(drift["checked"])
        self.assertEqual(drift["differs"], ["lynx_gnss"])
        self.assertEqual(drift["installed_not_in_source"], ["lynx_rogue"])


class CommandTest(unittest.TestCase):
    def run_main(self, argv):
        out = io.StringIO()
        with redirect_stdout(out):
            code = cov.main(argv)
        return code, out.getvalue()

    def test_json_and_text_from_saved_snapshot_are_reproducible(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "snap.json"
            path.write_text(json.dumps(live_like_snapshot()))
            code1, first = self.run_main(["--status", str(path)])
            code2, second = self.run_main(["--status", str(path)])
            code3, text = self.run_main(["--status", str(path), "--text"])
        self.assertEqual((code1, code2, code3), (0, 0, 0))
        self.assertEqual(first, second)
        self.assertEqual(json.loads(first)["tool_count"], 38)
        self.assertIn("action lynx_codex (agent/*): missing stop", text)
        self.assertIn("not ready hardware/flashlight: driver_not_loaded", text)
        self.assertIn("attended (separate): haptic-pulse-2026-11-21", text)

    def test_bad_inputs_fail_with_json_error(self):
        with TemporaryDirectory() as temp:
            bad = Path(temp) / "bad.json"
            bad.write_text("not json")
            code, out = self.run_main(["--status", str(bad)])
            self.assertEqual(code, 1)
            self.assertFalse(json.loads(out)["ok"])
            src = Path(temp) / "src"
            shutil.copytree(SOURCE, src)
            (src / "lynx_gnss.sh").unlink()
            code, out = self.run_main(["--source", str(src), "--no-status"])
            self.assertEqual(code, 1)
            self.assertIn("pairs differ", json.loads(out)["error"])


if __name__ == "__main__":
    unittest.main()
