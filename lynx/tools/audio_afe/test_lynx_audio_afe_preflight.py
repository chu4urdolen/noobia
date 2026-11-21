#!/usr/bin/env python3
"""Unit tests for the Lynx audio AFE PCM & DSP core preflight gate (D23)."""

import ast
import json
from pathlib import Path
import subprocess
import sys
import unittest

from lynx_audio_afe_preflight import (
    EXPECTED_AFE_COMPATIBLE,
    EXPECTED_AFE_IRQ,
    EXPECTED_AFE_NODE_NAME,
    EXPECTED_AFE_POWER_DOMAIN,
    EXPECTED_AFE_REG_BASE,
    EXPECTED_AFE_CLOCK_SOURCES,
    EXPECTED_SCP_COMPATIBLE,
    EXPECTED_SCP_DL_MEMIF_ID,
    EXPECTED_SCP_UL_MEMIF_ID,
    EXPECTED_SOUND_COMPATIBLE,
    EXPECTED_SOUND_PLATFORM,
    LIVE_COLLECT_SCRIPT,
    evaluate_audio_afe_preflight,
    validate_audio_afe_spec,
)

HERE = Path(__file__).resolve().parent
FIXTURES_DIR = HERE / "fixtures"
TOOL = HERE / "lynx_audio_afe_preflight.py"


def spec_doc() -> dict:
    """Return a valid board-spec document (from the sound-ready fixture)."""
    return json.loads((FIXTURES_DIR / "audio-afe-sound-ready.json").read_text())


class TestExpectedConstants(unittest.TestCase):
    def test_afe_identity_matches_mt6983_dts(self):
        # mt6983.dts:13828-13840
        self.assertEqual(EXPECTED_AFE_NODE_NAME, "mt6983-afe-pcm@1e100000")
        self.assertEqual(EXPECTED_AFE_COMPATIBLE, "mediatek,mt6983-sound")
        self.assertEqual(EXPECTED_AFE_REG_BASE, "0x1e100000")
        self.assertEqual(EXPECTED_AFE_IRQ, 448)
        self.assertEqual(EXPECTED_AFE_POWER_DOMAIN, "MT6983_POWER_DOMAIN_AUDIO")

    def test_afe_clock_sources_match_mt6983_dts(self):
        self.assertEqual(
            tuple(EXPECTED_AFE_CLOCK_SOURCES),
            ("topckgen", "apmixedsys", "infracfg_ao_clk"),
        )

    def test_scp_ultra_identity_matches_mt6983_dts(self):
        # mt6983.dts:13984-13988
        self.assertEqual(EXPECTED_SCP_COMPATIBLE, "mediatek,snd_scp_ultra")
        self.assertEqual(EXPECTED_SCP_DL_MEMIF_ID, 0x7)
        self.assertEqual(EXPECTED_SCP_UL_MEMIF_ID, 0xF)

    def test_sound_machine_identity_matches_mt6983_dts(self):
        self.assertEqual(EXPECTED_SOUND_COMPATIBLE, "mediatek,mt6983-mt6338-sound")
        self.assertEqual(EXPECTED_SOUND_PLATFORM, "afe")


class TestSpecValidation(unittest.TestCase):
    def test_valid_spec_passes(self):
        ok, failures = validate_audio_afe_spec(spec_doc())
        self.assertTrue(ok, failures)
        self.assertEqual(failures, [])

    def test_missing_afe_node_rejected(self):
        doc = spec_doc()
        doc["device_tree"]["afe_node_present"] = False
        ok, failures = validate_audio_afe_spec(doc)
        self.assertFalse(ok)
        self.assertIn("missing_afe_node_in_dt", failures)

    def test_corrupted_afe_compatible_rejected(self):
        doc = spec_doc()
        doc["device_tree"]["afe_compatible"] = "mediatek,mt6983-codec"
        ok, failures = validate_audio_afe_spec(doc)
        self.assertFalse(ok)
        self.assertTrue(any(f.startswith("afe_compatible_mismatch") for f in failures))

    def test_corrupted_afe_irq_rejected(self):
        doc = spec_doc()
        doc["device_tree"]["afe_irq"] = 512
        ok, failures = validate_audio_afe_spec(doc)
        self.assertFalse(ok)
        self.assertTrue(any(f.startswith("afe_irq_mismatch") for f in failures))

    def test_corrupted_afe_reg_base_rejected(self):
        doc = spec_doc()
        doc["device_tree"]["afe_reg_base"] = "0x1e200000"
        ok, failures = validate_audio_afe_spec(doc)
        self.assertFalse(ok)
        self.assertTrue(any(f.startswith("afe_reg_base_mismatch") for f in failures))

    def test_corrupted_power_domain_rejected(self):
        doc = spec_doc()
        doc["device_tree"]["afe_power_domain"] = "MT6983_POWER_DOMAIN_VIDEO"
        ok, failures = validate_audio_afe_spec(doc)
        self.assertFalse(ok)
        self.assertTrue(any(f.startswith("afe_power_domain_mismatch") for f in failures))

    def test_missing_clock_source_rejected(self):
        doc = spec_doc()
        doc["device_tree"]["afe_clock_sources"] = ["topckgen"]
        ok, failures = validate_audio_afe_spec(doc)
        self.assertFalse(ok)
        self.assertIn("afe_clock_source_missing_apmixedsys", failures)
        self.assertIn("afe_clock_source_missing_infracfg_ao_clk", failures)

    def test_corrupted_scp_compatible_rejected(self):
        doc = spec_doc()
        doc["device_tree"]["scp_compatible"] = "mediatek,snd_scp"
        ok, failures = validate_audio_afe_spec(doc)
        self.assertFalse(ok)
        self.assertTrue(any(f.startswith("scp_compatible_mismatch") for f in failures))

    def test_corrupted_scp_memif_ids_rejected(self):
        doc = spec_doc()
        doc["device_tree"]["scp_dl_memif_id"] = 0x1
        doc["device_tree"]["scp_ul_memif_id"] = 0x5
        ok, failures = validate_audio_afe_spec(doc)
        self.assertFalse(ok)
        self.assertTrue(any(f.startswith("scp_dl_memif_mismatch") for f in failures))
        self.assertTrue(any(f.startswith("scp_ul_memif_mismatch") for f in failures))

    def test_corrupted_sound_compatible_rejected(self):
        doc = spec_doc()
        doc["device_tree"]["sound_compatible"] = "mediatek,mt6983-mt6358-sound"
        ok, failures = validate_audio_afe_spec(doc)
        self.assertFalse(ok)
        self.assertTrue(any(f.startswith("sound_compatible_mismatch") for f in failures))

    def test_corrupted_sound_platform_rejected(self):
        doc = spec_doc()
        doc["device_tree"]["sound_platform"] = "mt2701-afe"
        ok, failures = validate_audio_afe_spec(doc)
        self.assertFalse(ok)
        self.assertTrue(any(f.startswith("sound_platform_mismatch") for f in failures))

    def test_missing_device_tree_section_rejected(self):
        ok, failures = validate_audio_afe_spec({})
        self.assertFalse(ok)
        self.assertIn("missing_afe_node_in_dt", failures)


class TestEvaluator(unittest.TestCase):
    def test_sound_ready_fixture(self):
        data = json.loads((FIXTURES_DIR / "audio-afe-sound-ready.json").read_text())
        v = evaluate_audio_afe_preflight(data)
        self.assertEqual(v.status, "SOUND_READY")
        self.assertTrue(v.is_valid)
        self.assertTrue(v.pcm_enumerated)
        self.assertTrue(v.stream_quiescent)

    def test_unbound_fixture_classifies_quiescent(self):
        data = json.loads((FIXTURES_DIR / "audio-afe-unbound.json").read_text())
        v = evaluate_audio_afe_preflight(data)
        self.assertEqual(v.status, "UNBOUND_QUIESCENT")
        self.assertTrue(v.is_valid)
        self.assertFalse(v.runtime_proc_present)

    def test_partial_enumeration_classification(self):
        data = json.loads((FIXTURES_DIR / "audio-afe-partial.json").read_text())
        v = evaluate_audio_afe_preflight(data)
        self.assertEqual(v.status, "PARTIAL_ENUMERATED")
        self.assertTrue(v.is_valid)
        self.assertTrue(v.runtime_proc_present)
        self.assertFalse(v.pcm_enumerated)

    def test_stream_active_is_safety_anomaly(self):
        data = json.loads((FIXTURES_DIR / "audio-afe-stream-active.json").read_text())
        v = evaluate_audio_afe_preflight(data)
        self.assertEqual(v.status, "STREAM_ACTIVE")
        self.assertFalse(v.is_valid)
        self.assertIn("stream_not_quiescent", v.failures)

    def test_missing_runtime_section_defaults_to_unbound_quiescent(self):
        data = json.loads((FIXTURES_DIR / "audio-afe-sound-ready.json").read_text())
        del data["runtime"]
        v = evaluate_audio_afe_preflight(data)
        self.assertEqual(v.status, "UNBOUND_QUIESCENT")
        self.assertTrue(v.stream_quiescent)

    def test_malformed_spec_fixture_rejected(self):
        data = json.loads((FIXTURES_DIR / "audio-afe-missing-dt.json").read_text())
        v = evaluate_audio_afe_preflight(data)
        self.assertEqual(v.status, "MALFORMED_SPEC")
        self.assertFalse(v.is_valid)
        self.assertTrue(v.failures)

    def test_to_dict_contains_all_fields(self):
        v = evaluate_audio_afe_preflight(spec_doc())
        d = v.to_dict()
        for key in (
            "status", "is_valid", "afe_node_mapped", "scp_node_mapped",
            "sound_node_mapped", "runtime_proc_present", "pcm_enumerated",
            "stream_quiescent", "summary", "failures", "details",
        ):
            self.assertIn(key, d)


class TestCli(unittest.TestCase):
    def run_tool(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(TOOL), *args],
            capture_output=True, text=True, timeout=30,
        )

    def test_cli_fixture_sound_ready_exit_zero(self):
        res = self.run_tool(str(FIXTURES_DIR / "audio-afe-sound-ready.json"))
        self.assertEqual(res.returncode, 0, res.stderr)
        payload = json.loads(res.stdout)
        self.assertEqual(payload["status"], "SOUND_READY")

    def test_cli_fixture_unbound_exit_zero(self):
        res = self.run_tool(str(FIXTURES_DIR / "audio-afe-unbound.json"))
        self.assertEqual(res.returncode, 0, res.stderr)
        payload = json.loads(res.stdout)
        self.assertEqual(payload["status"], "UNBOUND_QUIESCENT")

    def test_cli_fixture_partial_exit_zero(self):
        res = self.run_tool(str(FIXTURES_DIR / "audio-afe-partial.json"))
        self.assertEqual(res.returncode, 0, res.stderr)
        payload = json.loads(res.stdout)
        self.assertEqual(payload["status"], "PARTIAL_ENUMERATED")

    def test_cli_fixture_missing_dt_exit_one(self):
        res = self.run_tool(str(FIXTURES_DIR / "audio-afe-missing-dt.json"))
        self.assertEqual(res.returncode, 1)
        payload = json.loads(res.stdout)
        self.assertEqual(payload["status"], "MALFORMED_SPEC")

    def test_cli_fixture_stream_active_exit_one(self):
        res = self.run_tool(str(FIXTURES_DIR / "audio-afe-stream-active.json"))
        self.assertEqual(res.returncode, 1)
        payload = json.loads(res.stdout)
        self.assertEqual(payload["status"], "STREAM_ACTIVE")

    def test_cli_live_gate_requires_allow_live(self):
        res = self.run_tool("--live", "--host", "127.0.0.1")
        self.assertEqual(res.returncode, 2)
        self.assertIn("--allow-live", res.stderr)

    def test_cli_no_args_prints_help(self):
        res = self.run_tool()
        self.assertEqual(res.returncode, 0)
        self.assertIn("usage:", res.stdout.lower())


class TestSafetyBoundaries(unittest.TestCase):
    def test_live_script_is_readonly(self):
        forbidden = (
            "insmod", "rmmod", "modprobe", "setprop", "reboot", "shutdown",
            "kill", "tee", " > /sys", " > /proc", " > /etc", "dd of=",
            "mkfs", "rm -", "mv ", "cp ",
        )
        for token in forbidden:
            self.assertNotIn(token, LIVE_COLLECT_SCRIPT,
                             f"forbidden token in live script: {token}")

    def test_live_script_uses_only_whitelisted_commands(self):
        allowed = {"cat", "ls", "find", "readlink", "tr", "echo",
                   "for", "do", "done", "true", "sh"}
        import re
        commands = set(
            re.findall(r"^\s*([a-z_][a-z0-9_]*)\s", LIVE_COLLECT_SCRIPT,
                       flags=re.MULTILINE)
        )
        for cmd in commands:
            self.assertIn(cmd, allowed,
                          f"non-whitelisted command in live script: {cmd}")

    def test_live_script_opens_no_stream_and_writes_nothing(self):
        # Opening a stream means arecord/aplay/pcm writes; plain reads of
        # /proc/asound are fine. No audio capture/playback command allowed.
        for token in ("arecord", "aplay", "speaker-test", " > /dev/snd"):
            self.assertNotIn(token, LIVE_COLLECT_SCRIPT)
        self.assertNotIn(" > /proc", LIVE_COLLECT_SCRIPT)
        self.assertNotIn(" > /sys", LIVE_COLLECT_SCRIPT)

    def test_tool_imports_are_harmless(self):
        tree = ast.parse(TOOL.read_text())
        allowed_modules = {
            "dataclasses", "json", "pathlib", "subprocess", "sys", "typing",
            "argparse",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertIn(alias.name.split(".")[0], allowed_modules)
            elif isinstance(node, ast.ImportFrom):
                self.assertIn((node.module or "").split(".")[0], allowed_modules)

    def test_no_unapproved_local_calls(self):
        local_calls = HERE.parent / "local_calls"
        if not local_calls.is_dir():
            self.skipTest("local_calls directory absent")
        # The preflight tool must not be wired into the agent catalog.
        for p in local_calls.rglob("*"):
            if not p.is_file():
                continue
            content = p.read_text()
            self.assertNotIn("lynx_audio_afe_preflight", content,
                             f"preflight referenced in {p.name}")
            self.assertNotIn("tools/audio_afe", content,
                             f"tools/audio_afe referenced in {p.name}")


if __name__ == "__main__":
    unittest.main()
